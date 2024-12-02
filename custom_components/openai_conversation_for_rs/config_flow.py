"""Config flow for the Azure OpenAI GPT conversation RS-Tuned integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_API_KEY
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from openai import AsyncAzureOpenAI

from .const import (
    API_VERSION,
    CONF_DEPLOYMENT_NAME,
    CONF_ENDPOINT,
    CONVERSATION_AGENT_NAME,
    DOMAIN,
    FIXED_ENDPOINT,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Required(CONF_DEPLOYMENT_NAME): str,
    }
)


class AzureOpenAIConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Azure OpenAI."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._errors = {}

    async def _validate_input(self, data: dict[str, Any]) -> dict[str, Any]:
        """Validate the user input allows us to connect."""
        try:
            client = AsyncAzureOpenAI(
                api_key=data[CONF_API_KEY], api_version=API_VERSION, azure_endpoint=FIXED_ENDPOINT
            )

            # Test connection with a simple request
            response = await client.chat.completions.create(
                model=data[CONF_DEPLOYMENT_NAME], messages=[{"role": "user", "content": "test"}], max_tokens=5
            )

            return {"title": f"{CONVERSATION_AGENT_NAME} ({data[CONF_DEPLOYMENT_NAME]})"}

        except Exception as err:
            _LOGGER.error("Unexpected error occurred: %s", err)
            if "Status code: 401" in str(err):
                self._errors["base"] = "invalid_auth"
                raise InvalidAuth
            else:
                self._errors["base"] = "cannot_connect"
                raise CannotConnect

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle the initial step."""
        self._errors = {}

        if user_input is not None:
            user_input[CONF_ENDPOINT] = FIXED_ENDPOINT
            try:
                info = await self._validate_input(user_input)
                await self.async_set_unique_id(f"{FIXED_ENDPOINT}_{user_input[CONF_DEPLOYMENT_NAME]}")
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                )
            except CannotConnect:
                self._errors["base"] = "cannot_connect"
            except InvalidAuth:
                self._errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                self._errors["base"] = "unknown"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=self._errors,
        )

    async def async_step_import(self, user_input: dict[str, Any]) -> FlowResult:
        """Handle import from configuration.yaml."""
        return await self.async_step_user(user_input)


class ConfigEntryError(HomeAssistantError):
    """Error while setting up an entry from configuration."""


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
