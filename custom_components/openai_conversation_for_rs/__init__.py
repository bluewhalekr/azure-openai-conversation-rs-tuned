"""The Azure OpenAI GPT conversation RS-Tuned integration."""

import json
import logging

from homeassistant.components import conversation, intent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.typing import ConfigType
from openai import AsyncAzureOpenAI

from .const import CONF_DEPLOYMENT_NAME, DOMAIN, FIXED_ENDPOINT
from .ha_crawler import HaCrawler
from .prompt import template as prompt_template

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
        # token과 base url 확보를 위한 ConfigEntry를 HaCrawler에 전달
        self.ha_crawler = HaCrawler(hass, entry)

    def _format_ha_context(self, ha_states: dict) -> str:
        """Format Home Assistant context for the prompt."""
        context = f"Current Time: {ha_states.get('time', 'unknown')}\n"
        context += f"Date: {ha_states.get('date', 'unknown')}\n"
        context += f"Day: {ha_states.get('weekday', 'unknown')}\n\n"

        context += "Available Devices:\n"
        for entity in ha_states.get("entities", []):
            area_name = entity.get("area", {}).get("name", "Unknown Area")
            context += f"- {entity['name']} ({entity['entity_id']}) in {area_name}\n" f"  State: {entity['state']}\n"

        return context

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return ["en", "ko"]

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
                context = "Unable to fetch current home state."

            # Enhanced system prompt with HA context
            system_prompt = f"""{prompt_template}

Current Home State:
{context}

Available Services:
{[f"{service['domain']}.{list(service.get('services', {}).keys())}" for service in ha_services]}

When you need to control devices, respond with a JSON object in this format:
{{
    "action": "call_service",
    "domain": "[domain]",
    "service": "[service]",
    "entity_id": "[entity_id]",
    "response": "[human readable response]"
}}

Only use services and entities that exist in the current context."""

            messages = [
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": user_input.text},
            ]

            response_text = await self._get_azure_response(messages)

            # Try to parse response as JSON for device control
            try:
                response_data = json.loads(response_text)
                if response_data.get("action") == "call_service":
                    await self.hass.services.async_call(
                        domain=response_data["domain"],
                        service=response_data["service"],
                        target={"entity_id": response_data["entity_id"]},
                        blocking=True,
                    )
                    response_text = response_data["response"]
            except json.JSONDecodeError:
                # Not a JSON response, use as is
                pass

            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_speech(response_text)
            return conversation.ConversationResult(response=intent_response, conversation_id=user_input.conversation_id)

        except Exception as err:
            _LOGGER.error("Error processing with Azure OpenAI GPT-4-mini: %s", err)
            intent_response = intent.IntentResponse(language=user_input.language)
            intent_response.async_set_error(
                intent.IntentResponseErrorCode.UNKNOWN,
                f"Sorry, I had a problem talking to OpenAI: {err}",
            )
            return conversation.ConversationResult(response=intent_response, conversation_id=self.entry.entry_id)

    async def _get_azure_response(self, messages: list) -> str:
        """Get response from Azure OpenAI."""
        try:
            response = await self.client.chat.completions.create(model=self.deployment_name, messages=messages)
            return response.choices[0].message.content
        except Exception as err:
            _LOGGER.error("Failed to get response from Azure OpenAI GPT-4-mini: %s", err)
            raise
