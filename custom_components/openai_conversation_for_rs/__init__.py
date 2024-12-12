"""The Azure OpenAI GPT conversation RS-Tuned integration."""

import logging
import traceback

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
from .message_model import AssistantMessage, SystemMessage, UserMessage
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
        self.hass_api_handler = HassApiHandler(hass)

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

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        """Process a sentence."""
        response_text = ""
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

            if chat_response:
                call_service_count = 0

                response_message = chat_response.choices[0].message
                assistant_message = AssistantMessage(**response_message.to_dict())
                if assistant_message.content:
                    response_text = assistant_message.content
                chat_manager.add_message(assistant_message)
                if tool_calls := assistant_message.tool_calls:
                    for tool_call in tool_calls:
                        call_service_count += 1
                        _LOGGER.info("tool_call: %s", tool_call)
                        api_call = tool_call.function.arguments
                        _LOGGER.info("api_call: %s", api_call)

                        await self.hass_api_handler.process_api_call(tool_call.function)
                # TODO manually return response_text
                if "youtube_domain_flg" in response_text:
                    intent_response = intent.IntentResponse(language=user_input.language)
                    intent_response.async_set_speech(speech=user_input.text, extra_data={"type": "chrome"})
                else:
                    if call_service_count > 1:
                        response_text = "요청하신 명령을 수행합니다."
                    intent_response = intent.IntentResponse(language=user_input.language)
                    intent_response.async_set_speech(response_text, extra_data={"type": "gpt"})
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


class HassApiHandler:
    """Home Assistant API 처리를 위한 핸들러."""

    def __init__(self, hass):
        """Initialize the handler."""
        self.hass = hass

    async def process_api_call(self, api_call):
        """Process an API call.

        Args:
            api_call:  API 호출 객체

        Returns:
            bool: True if successful, False if failed

        """
        # ApiCallFunction인 경우 arguments 추출
        if hasattr(api_call, "arguments"):
            api_call = api_call.arguments

        # API 호출 변환
        service_params = self._convert_to_hass_api_call(api_call)
        if service_params:
            # Home Assistant 서비스 호출 실행
            try:
                await self.hass.services.async_call(
                    domain=service_params["domain"],
                    service=service_params["service"],
                    target=service_params.get("target"),
                    service_data=service_params.get("service_data"),
                    blocking=True,
                )
                return True
            except Exception as err:
                _LOGGER.error("Failed to call Home Assistant service: %s", str(err))
                return False
        return False

    def _convert_to_hass_api_call(self, api_call):
        """Convert API 호출을 Home Assistant 형식."""
        parts = api_call.endpoint.split("/")

        # 서비스 호출 변환 (/api/services/...)
        if len(parts) >= 5 and parts[2] == "services":
            return self._convert_service_call(api_call)

        # 자동화 설정 변환 (/api/config/automation/...)
        elif len(parts) >= 4 and parts[2] == "config" and parts[3] == "automation":
            return self._convert_automation_call(api_call)

        return None

    def _convert_service_call(self, api_call):
        """서비스 API 호출 변환."""
        parts = api_call.endpoint.split("/")
        domain = parts[3]
        service = parts[4]

        # service_data에서 entity_id 분리
        service_data = dict(api_call.body)
        entity_id = service_data.pop("entity_id", None)

        result = {"domain": domain, "service": service}

        # entity_id가 있는 경우 target에 포함
        if entity_id:
            result["target"] = {"entity_id": entity_id}

        # 추가 서비스 데이터가 있는 경우에만 포함
        if service_data:
            result["service_data"] = service_data

        return result

    def _convert_automation_call(self, api_call):
        """자동화 설정 API 호출 변환."""
        automation_config = {
            "alias": api_call.body["alias"],
            "description": "Automatically created automation",
            "trigger": api_call.body["trigger"],
            "action": api_call.body["action"],
            "mode": "single",
            "id": api_call.body["alias"],
        }

        return {"domain": "automation", "service": "create", "target": None, "service_data": automation_config}
