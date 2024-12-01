"""The Azure OpenAI GPT conversation RS-Tuned integration."""

import logging

from homeassistant.components import conversation, intent
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.helpers.typing import ConfigType
from openai import AsyncAzureOpenAI

from .const import CONF_DEPLOYMENT_NAME, DOMAIN, FIXED_ENDPOINT
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

    @property
    def supported_languages(self) -> list[str]:
        """Return a list of supported languages."""
        return ["en", "ko"]

    async def async_process(self, user_input: conversation.ConversationInput) -> conversation.ConversationResult:
        """Process a sentence."""
        try:
            messages = [
                {
                    "role": "system",
                    "content": prompt_template,
                },
                {"role": "user", "content": user_input.text},
            ]

            response_text = await self._get_azure_response(messages)
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
