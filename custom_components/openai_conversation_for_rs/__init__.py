"""The Azure OpenAI GPT conversation RS-Tuned integration."""

import json
import logging
import traceback
import uuid
from collections.abc import Callable
from typing import Any

import aiohttp
import netifaces
import yaml
from homeassistant.components import conversation, mqtt
from homeassistant.components.automation import DOMAIN as AUTOMATION_DOMAIN
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import intent
from homeassistant.helpers.condition import async_from_config
from homeassistant.helpers.typing import ConfigType
from openai import AsyncAzureOpenAI

from .chat_manager import ChatManager
from .const import (
    BLENDER_BRIDGE_ENDPOINT,
    BLENDER_DEVICE_ENTITY,
    BLENDER_LIGHT_ENTITY,
    CACHE_ENDPOINT,
    CONF_DEPLOYMENT_NAME,
    DOMAIN,
    FIXED_ENDPOINT,
)
from .ha_crawler import HaCrawler
from .message_model import AssistantMessage, SystemMessage, ToolMessage, UserMessage
from .prompt_generator import GptHaAssistant, PromptGenerator
from .prompt_manager import PromptManager

_LOGGER = logging.getLogger(__name__)
_LOGGER.setLevel(logging.DEBUG)
SYSTEM_MAC_ADDRESS = netifaces.ifaddresses("end0")[netifaces.AF_PACKET][0]["addr"]


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

            speaker_id = SYSTEM_MAC_ADDRESS
            if user_input.text:
                user_input_text = user_input.text.split("||")
                if len(user_input_text) == 2:
                    user_input.text = user_input_text[1]
                    speaker_id = user_input_text[0]

            _LOGGER.info("speaker_id: %s", speaker_id)
            _LOGGER.info("input_text: %s", user_input.text)

            # TODO show speaker recognition for demo, have to remove after demo
            self.hass.async_create_task(self._publish_speaker_status(speaker_id[-2:], user_input.text))

            chat_manager = ChatManager(speaker_id)
            chat_manager.add_message(UserMessage(content=user_input.text))

            # Check to cache, when user_input.text is hitted.
            cached_response = await self.send_cache_request(speaker_id, user_input.text)
            if cached_response:
                _LOGGER.info("cached_response: %s", cached_response)
                if not cached_response.get("role"):  # role은 필수 필드
                    raise RuntimeError("Missing required 'role' field in cached response Data")

                assistant_message = AssistantMessage(**cached_response)

            else:
                chat_manager = ChatManager(speaker_id)
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
                # 만약 입력단에 || 가 포함되어 있으면 speaker_id가 포함된 것을 간주

                chat_manager.add_message(SystemMessage(**system_datetime_prompt))
                # chat_manager.add_message(SystemMessage(**system_entities_prompt))
                # chat_manager.add_message(SystemMessage(**system_services_prompt))

                chat_input_messages = chat_manager.get_chat_input()
                chat_input_messages.append(system_entities_prompt)
                chat_input_messages.append(system_services_prompt)

                for i in range(len(chat_input_messages)):
                    _LOGGER.info("chat_input_messages-%s: %s", i, chat_input_messages[i])
                chat_response = await gpt_ha_assistant.chat(chat_input_messages)
                _LOGGER.info("chat_response: %s", chat_response)

                assistant_message = AssistantMessage()
                if isinstance(chat_response, str):
                    # Handle string response
                    assistant_message = AssistantMessage(content=chat_response, role="assistant")
                elif chat_response and hasattr(chat_response, "choices") and isinstance(chat_response.choices, list):
                    response_message = chat_response.choices[0].message
                    assistant_message = AssistantMessage(**response_message.to_dict())

            call_service_count = 0

            if assistant_message.content:
                response_text = assistant_message.content

            chat_manager.add_message(assistant_message)
            if tool_calls := assistant_message.tool_calls:
                for tool_call in tool_calls:
                    call_service_count += 1
                    _LOGGER.info("tool_call: %s", tool_call)
                    api_call = tool_call.function.arguments
                    _LOGGER.info("api_call: %s", api_call)

                    tool_call_result: bool = await self.hass_api_handler.process_api_call(tool_call.function)
                    tool_call_message_content = "Success" if tool_call_result else "Failed"
                    tool_message = ToolMessage(tool_call_id=tool_call.id, content=tool_call_message_content)
                    chat_manager.add_message(tool_message)

            # TODO manually return response_text
            if "googlecast_domain_flg" in response_text:
                intent_response = intent.IntentResponse(language=user_input.language)
                intent_response.async_set_speech(speech=user_input.text, extra_data={"type": "chrome"})
            else:
                if call_service_count > 1:
                    response_text = "요청하신 명령을 수행합니다."
                intent_response = intent.IntentResponse(language=user_input.language)
                intent_response.async_set_speech(response_text, extra_data={"type": "gpt"})
                self.hass.async_create_task(
                    self._publish_speaker_status(speaker_id[-2:], user_input.text, response_text)
                )
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

    async def _publish_speaker_status(self, speaker_id: str, message: str, response: str = "") -> None:
        """Publish speaker status to MQTT."""
        payload = {"current": speaker_id, "message": message, "response": response}

        # MQTT 메시지 발행
        await mqtt.async_publish(
            self.hass, topic="home/speaker/status", payload=json.dumps(payload), qos=0, retain=False
        )

    async def send_cache_request(self, speaker_id: str, input_text: str):
        """Send cache request to the cache server.

        Args:
            speaker_id: speaker_id is consist of mac address and user_id
            input_text: user input,

        Returns:
            dict: response from the cache server

        """
        headers = {"x-functions-key": self.entry.data[CONF_API_KEY], "Content-Type": "application/json"}
        data = {"speaker_id": speaker_id, "input_text": input_text}
        _LOGGER.info("Cache request: %s", data)
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(CACHE_ENDPOINT, json=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()
                        _LOGGER.info("Response: %s", result)
                        return result
                    _LOGGER.info("Failed with status code: %s", response.status)
                    error_text = await response.text()
                    _LOGGER.info("Error response: %s", error_text)
                    return None
            except Exception:
                _LOGGER.error(traceback.format_exc())
                return None


class HassApiHandler:
    """Home Assistant API 처리를 위한 핸들러."""

    def __init__(self, hass):
        """Initialize the handler."""
        self.hass = hass

    async def create_if_action(self, condition_config: list[dict]) -> Callable:
        """IfAction 형식의 조건 함수 생성"""
        if not condition_config:
            # 조건이 없는 경우 항상 True를 반환하는 함수 반환
            @callback
            def always_true(*args: Any, **kwargs: Any) -> bool:
                return True

            return always_true

        cond = await async_from_config(self.hass, condition_config)

        @callback
        def if_action(*args: Any, **kwargs: Any) -> bool:
            """IfAction 형식을 만족하는 래퍼 함수"""
            try:
                return cond(*args, **kwargs)
            except Exception as e:
                _LOGGER.error("Error executing condition: %s", str(e))
                return False

        return if_action

    def save_automation_to_yaml(self, automation_config):
        """Save automation to automations.yaml."""
        yaml_path = self.hass.config.path("automations.yaml")

        try:
            # 기존 automations.yaml 내용 읽기
            with open(yaml_path) as file:
                existing_data = yaml.safe_load(file) or []

            # 새로운 자동화 추가
            existing_data.append(automation_config)

            # 업데이트된 내용 저장
            with open(yaml_path, "w") as file:
                yaml.dump(existing_data, file, default_flow_style=False)

            _LOGGER.info("Automation saved to automations.yaml: %s", automation_config["id"])
        except Exception as e:
            _LOGGER.error("Failed to save automation to YAML: %s", e)

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

        parts = api_call.endpoint.split("/")

        if len(parts) >= 5 and parts[2] == "services":
            service_params = self._convert_service_call(api_call)
            if service_params:
                # Home Assistant 서비스 호출 실행
                try:
                    await self.hass.services.async_call(
                        domain=service_params["domain"],
                        service=service_params["service"],
                        target=service_params.get("target", {}),
                        service_data=service_params.get("service_data"),
                        blocking=True,
                    )
                    return True
                except Exception as err:
                    _LOGGER.error("Failed to call Home Assistant service: %s", str(err))
                    return False
        if len(parts) >= 4 and parts[2] == "config" and parts[3] == "automation":
            try:
                automation_config = self._convert_automation_call(api_call)
                if "id" not in automation_config:
                    automation_config["id"] = str(uuid.uuid4())
                # automations.yaml에 저장
                self.save_automation_to_yaml(automation_config)
                # 자동화 컴포넌트 재로드
                await self.hass.services.async_call("automation", "reload")
                return True
            except Exception as e:
                _LOGGER.error("Failed to create automation: %s", e)
                return False
        return False

    def _convert_service_call(self, api_call):
        """서비스 API 호출 변환."""
        parts = api_call.endpoint.split("/")
        domain = parts[3]
        service = parts[4]

        async def _synch_blender_bridge():
            """블렌더 브릿지 동기화."""
            parts = api_call.endpoint.split("/")
            service = parts[4]

            # service_data에서 entity_id 분리
            service_data = dict(api_call.body)
            entity_id = service_data.pop("entity_id", None)

            if entity_id is not None:
                entity_id = entity_id.split(".")[1]

            path = "/control-light"
            if entity_id in BLENDER_LIGHT_ENTITY:
                path = "/control-light"
            elif entity_id in BLENDER_DEVICE_ENTITY or service == "vacuum_stop_and_return":
                path = "/control-device"
            else:
                return None

            if service in ["turn_on", "start"]:
                status = "on"
            elif service == "turn_off":
                status = "off"
            elif service == "vacuum_stop_and_return" and entity_id is None:
                status = "off"
                entity_id = "robosceongsogi"
            else:
                return None

            data = {"name": entity_id, "status": status}
            _LOGGER.info("blender request: %s", data)
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.post(BLENDER_BRIDGE_ENDPOINT + path, json=data) as response:
                        if response.status == 200:
                            result = await response.json()
                            _LOGGER.info("Response: %s", result)
                            return result
                        _LOGGER.info("Failed with status code: %s", response.status)
                        error_text = await response.text()
                        _LOGGER.info("Error response: %s", error_text)
                        return None
                except Exception:
                    _LOGGER.error(traceback.format_exc())
                    return None

        self.hass.async_create_task(_synch_blender_bridge())
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
        """api_call 데이터를 Home Assistant 서비스 호출 데이터로 변환합니다."""
        # 입력 데이터 검증
        if api_call.method.lower() != "post":
            return None

        # endpoint에서 automation ID 추출
        endpoint = api_call.endpoint
        automation_alias = endpoint.split("/")[-1]

        # body 데이터를 service_data로 변환
        body = api_call.body

        automation_id = f"automation.auto_{str(uuid.uuid4())[:8]}"

        # automation.create 서비스에 필요한 데이터 구성
        config = {
            "id": automation_id,
            "alias": automation_alias,
            "trigger": body.get("trigger"),
            "condition": body.get("condition"),
            "action": body.get("action"),
            "mode": "single",
        }

        return config
