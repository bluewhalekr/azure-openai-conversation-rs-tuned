"""The Azure OpenAI GPT conversation RS-Tuned integration."""

import json
import logging
import re
import traceback

import openai
from homeassistant.components import conversation, intent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.typing import ConfigType
from openai import AsyncAzureOpenAI

from .chat_manager import ChatManager
from .const import CONF_DEPLOYMENT_NAME, DOMAIN, FIXED_ENDPOINT
from .ha_crawler import HaCrawler
from .message_model import SystemMessage, UserMessage
from .prompt import template as prompt_template
from .prompt_generator import GptHaAssistant, PromptGenerator
from .prompt_manager import PromptManager

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up Azure OpenAI Component."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Azure OpenAI from a config entry."""
    client = AsyncAzureOpenAI(
        api_key=entry.data[CONF_API_KEY], api_version="2024-08-01-preview", azure_endpoint=FIXED_ENDPOINT
    )
    hass.data[DOMAIN][entry.entry_id] = client
    agent = AzureOpenAIAgent(hass, entry, client)
    conversation.async_set_agent(hass, entry, agent)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    conversation.async_unset_agent(hass, entry)
    hass.data[DOMAIN].pop(entry.entry_id)
    return True


class AzureOpenAIAgent(conversation.AbstractConversationAgent):
    """Azure OpenAI conversation agent."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: AsyncAzureOpenAI) -> None:
        """Initialize the agent."""
        self.hass = hass
        self.entry = entry
        self.client = client
        self.history = []
        self.deployment_name = entry.data[CONF_DEPLOYMENT_NAME]
        self.ha_crawler = HaCrawler(hass)
        self.prompt_manager = PromptManager(entry.entry_id)

    def _format_ha_context(self, ha_states: dict) -> str:
        """Format Home Assistant context for the prompt."""
        context = f"Current Time: {ha_states.get('time', 'unknown')}\n"
        context += f"Date: {ha_states.get('date', 'unknown')}\n"
        context += f"Day: {ha_states.get('weekday', 'unknown')}\n\n"

        context += "Available Devices:\n"
        for entity in ha_states.get("entities", []):
            area_name = (entity.get("area") or {}).get("name", "Unknown Area")
            context += f"- {entity['name']} ({entity['entity_id']}) in {area_name}\n" f"  State: {entity['state']}\n"

        return context

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return ["en", "ko"]

    async def _refine_response(self, response_text):
        """Refine various response formats."""
        try:
            if response_text is None:
                response_text = "OpenAI가 제 말을 이해하지 못했습니다. 다른 표현으로 다시 시도해주세요"
            response_text = response_text.strip()  # 공백 제거

            # Case 0: ```json ... ``` 형태 처리
            json_blocks = re.findall(r"```json(.*?)```", response_text, flags=re.DOTALL)

            if json_blocks:
                _LOGGER.info("Extracting JSON from code blocks.")
                # JSON 블록 추출 (```json과 ``` 제거)
                response_text = "\n".join(json_blocks)
                plain_text = re.sub(r"```json.*?```", "", response_text, flags=re.DOTALL).strip()
                if plain_text:
                    _LOGGER.info("plain text: %s", plain_text)

            # Case 1: JSON 배열 형식
            if response_text.startswith("[") and response_text.endswith("]"):
                _LOGGER.info("Processing JSON array format.")
                return response_text

            # Case 2: 쉼표로 나열된 JSON 객체
            if response_text.startswith("{") and response_text.endswith("}"):
                if "," in response_text:  # 쉼표가 있는 경우, JSON 배열로 변환
                    _LOGGER.info("Processing multiple JSON objects.")
                    return f"[{response_text}]"
                _LOGGER.info("Processing single JSON object.")  # 단일 객체
                return response_text

            # Case 3: 일반 문장
            _LOGGER.info("Processing plain text: %s", response_text)
            return response_text

        except Exception as e:
            _LOGGER.error("Error refining response: %s", e)
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return None

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        """Process a sentence."""
        try:
            # Get current HA states
            try:
                ha_states = self.ha_crawler.get_ha_states()
                ha_services = self.ha_crawler.get_services()
                context = self._format_ha_context(ha_states)

            except Exception as err:
                _LOGGER.error("Failed to get HA states: %s", err)
                _LOGGER.error("Traceback: %s", traceback.format_exc())
                context = "Unable to fetch current home state."

            chat_manager = ChatManager(self.entry.entry_id)
            prompt_generator = PromptGenerator(ha_states, ha_services)
            system_datetime_prompt = prompt_generator.get_datetime_prompt()
            system_entities_prompt = prompt_generator.get_entities_system_prompt()
            system_services_prompt = prompt_generator.get_services_system_prompt()

            gpt_ha_assistant = GptHaAssistant(
                deployment_name=self.deployment_name,
                init_prompt=self.prompt_manager.get_init_prompt(),
                ha_automation_script=self.prompt_manager.get_ha_automation_script(),
                user_pattern_prompt=self.prompt_manager.get_user_pattern_prompt(),
                tool_prompts=[prompt_generator.get_tool()],
                client=self.client,
            )

            chat_manager.add_message(UserMessage(content=user_input.text))
            chat_manager.add_message(SystemMessage(**system_datetime_prompt))
            chat_manager.add_message(SystemMessage(**system_entities_prompt))
            chat_manager.add_message(SystemMessage(**system_services_prompt))

            chat_input_messages = chat_manager.get_chat_input()
            _LOGGER.info("chat_input_messages: %s", chat_input_messages)
            chat_response = await gpt_ha_assistant.chat(chat_input_messages)
            _LOGGER.info("chat_response: %s", chat_response)

            # Enhanced system prompt with HA context
            system_prompt = f"""{prompt_template}

Current Home State:
{context}

Available Services:
{[f"{service['domain']}.{list(service.get('services', {}).keys())}" for service in ha_services]}

When you need to control devices, respond with a JSON array of objects in this format:
[
    {{
        "action": "call_service",
        "domain": "[domain]",
        "service": "[service]",
        "entity_id": "[entity_id]",
        "response": "[human readable response]"
    }},
    {{
        "action": "call_service",
        "domain": "[domain]",
        "service": "[service]",
        "entity_id": "[entity_id]",
        "response": "[human readable response]"
    }}
]

Only use services and entities that exist in the current context."""

            messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": user_input.text},
            ]

            response_text = await self._get_azure_response(messages)
            response_text = await self._refine_response(response_text)

            # Try to parse response as JSON for device 요control
            try:
                response_data = json.loads(response_text)
                # 복수 call_service가 올 수 있는 지 체크 필

                if isinstance(response_data, dict):
                    response_data = [response_data]  # 단일 객체를 리스트로 변환
                elif isinstance(response_data, str):
                    _LOGGER.info("Received plain text response: %s", response_text)
                    response_data = []  # 문자열은 처리할 JSON 데이터가 없으므로 빈 리스트로 설정

                # JSON 배열 또는 빈 리스트 처리
                call_service_count = 0
                for item in response_data:
                    if item.get("action") == "call_service":
                        _LOGGER.info("call_service: %s", item["service"])
                        await self.hass.services.async_call(
                            domain=item["domain"],
                            service=item["service"],
                            target={"entity_id": item["entity_id"]},
                            blocking=True,
                        )
                        response_text = item.get("response", "요청하신 명령을 수행합니다.")
                        call_service_count += 1
                        _LOGGER.info("response_text: %s", response_text)
                if call_service_count > 1:
                    response_text = "요청하신 명령을 수행합니다."
            except json.JSONDecodeError:
                # Not a JSON response, use as is
                _LOGGER.error("json.JSONDecodeError: %s", response_text)

            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(response_text)
            return conversation.ConversationResult(response=intent_response, conversation_id=user_input.conversation_id)

        except Exception as err:
            _LOGGER.error("Error processing with Azure OpenAI GPT-4-mini: %s", err)
            _LOGGER.error("user_input.text: %s", user_input.text)
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I had a problem talking to OpenAI: {err}",
            )
            return conversation.ConversationResult(response=intent_response, conversation_id=self.entry.entry_id)

    async def _get_azure_response(self, messages: list) -> str:
        """Get response from Azure OpenAI and handle content filtering errors.

        Args:
            messages (list): List of conversation messages

        Returns:
            str: Response content or error message

        """
        try:
            # Azure OpenAI API 호출
            response = await self.client.chat.completions.create(
                model=self.deployment_name, messages=messages, temperature=0.0
            )
            return response.choices[0].message.content

        except openai.BadRequestError as err:
            return await self._handle_bad_request_error(err)

        except openai.RateLimitError:
            _LOGGER.warning("Rate limit exceeded")
            return "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."

        except openai.APIError as err:
            _LOGGER.error("Azure OpenAI API Error: %s", str(err))
            return "서비스에 일시적인 문제가 발생했습니다. 잠시 후 다시 시도해주세요."

        except Exception as err:
            _LOGGER.error("Unexpected error: %s", str(err))
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return "알 수 없는 오류가 발생했습니다. 잠시 후 다시 시도해주세요."

    async def _handle_bad_request_error(self, err) -> str:
        """Handle BadRequestError and process content filtering results.

        Args:
            err (openai.BadRequestError): The error object

        Returns:
            str: Formatted error message for the user

        """
        default_message = "OpenAI가 제 말을 이해하지 못했습니다. 다른 표현으로 다시 시도해주세요."

        try:
            # 오류 데이터 파싱
            error_data = err.args[0]
            if not isinstance(error_data, str):
                _LOGGER.error("Unexpected error data type: %s", type(error_data))
                return default_message

            error_dict = json.loads(error_data)
            error_info = error_dict.get("error", {})

            # 기본 오류 정보 로깅
            _LOGGER.error("Azure OpenAI Error: %s", error_info.get("message", "Unknown error"))
            _LOGGER.error("Error Code: %s", error_info.get("code", "unknown_error"))

            # 콘텐츠 필터 결과 처리
            content_filter_result = error_info.get("innererror", {}).get("content_filter_result", {})
            if not content_filter_result:
                return default_message

            # 콘텐츠 필터 결과 로깅
            _LOGGER.error("Content Filter Result: %s", json.dumps(content_filter_result, indent=2))

            # 사용자 피드백 메시지 생성
            feedback_lines = [
                "요청이 Azure OpenAI의 콘텐츠 관리 정책에 의해 차단되었습니다. 다른 표현으로 요청해주세요."
            ]

            # 차단된 카테고리 정보 추가
            for category, details in content_filter_result.items():
                if details.get("filtered", False):
                    severity = details.get("severity", "unknown")
                    feedback_lines.append(f"- 차단된 카테고리: {category} (심각도: {severity})")

            return "\n".join(feedback_lines)

        except json.JSONDecodeError as json_err:
            _LOGGER.error("JSON parsing error: %s", str(json_err))
            return default_message

        except Exception as parse_err:
            _LOGGER.error("Error parsing response: %s", str(parse_err))
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return default_message
