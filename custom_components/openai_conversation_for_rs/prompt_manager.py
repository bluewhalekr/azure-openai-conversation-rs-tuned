"""Manage the prompts for the OpenAI conversation."""

import json
import os

from .const import DOMAIN

file_path = os.path.dirname(__file__)
INIT_PROMPT_PATH = os.path.join(os.path.dirname(file_path), DOMAIN, "prompts", "init_prompt.md")
USER_PATTERN_PROMPT_PATH = os.path.join(os.path.dirname(file_path), DOMAIN, "prompts", "user_pattern_prompt.md")
HA_AUTOMATION_SCRIPT_PATH = os.path.join(os.path.dirname(file_path), DOMAIN, "prompts", "ha_automation_script.md")

DATA_PATH = os.path.join(file_path, DOMAIN, "chat_configs")
HA_STATES_PATH = os.path.join(DATA_PATH, "ha_contexts", "states.json")
HA_SERVICES_PATH = os.path.join(DATA_PATH, "ha_contexts", "services.json")


class ClientCache:
    """Cache Structure for the client."""

    def __init__(self, client_id):
        self.client_id = client_id
        self._cache = {}

    def get(self, key, default=None):
        """Get the value from the cache."""
        return self._cache.get(key, default)

    def set(self, key, value):
        """Set the value in the cache."""
        self._cache[key] = value
        return self._cache


def load_json(path):
    """Load the JSON file."""
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_default_ha_states():
    """Get the default Home Assistant states."""
    return load_json(HA_STATES_PATH)


def get_default_ha_services():
    """Get the default Home Assistant services."""
    return load_json(HA_SERVICES_PATH)


def get_default_init_prompt():
    """Get the default init prompt."""
    with open(INIT_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def get_default_ha_automation_script():
    """Get the default Home Assistant automation script."""
    with open(HA_AUTOMATION_SCRIPT_PATH, encoding="utf-8") as f:
        return f.read()


def get_default_user_pattern_prompt():
    """Get the default last prompt."""
    with open(USER_PATTERN_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


class PromptManager:
    """Class to manage the prompts."""

    def __init__(self, client_id):
        self.client_id = client_id
        self.cache = ClientCache(client_id)

    def get_init_prompt(self):
        """Get the init prompt."""
        if prompt := self.cache.get("init_prompt"):
            return prompt

        return self.reset_init_prompt()

    def get_ha_automation_script(self):
        """Get the Home Assistant automation script."""
        if script := self.cache.get("ha_automation_script"):
            return script

        return self.reset_ha_automation_script()

    def get_user_pattern_prompt(self):
        """Get the last prompt."""
        if prompt := self.cache.get("user_pattern_prompt"):
            return prompt

        return self.reset_user_pattern_prompt()

    def set_init_prompt(self, prompt: str):
        """Set the init prompt."""
        self.cache.set("init_prompt", prompt)

    def set_user_pattern_prompt(self, prompt: str):
        """Set the last prompt."""
        self.cache.set("user_pattern_prompt", prompt)

    def reset_init_prompt(self):
        """Reset the init prompt."""
        default_init_prompt = get_default_init_prompt()
        self.cache.set("init_prompt", default_init_prompt)

        return self.cache.get("init_prompt")

    def reset_ha_automation_script(self):
        """Reset the Home Assistant automation script."""
        default_ha_automation_script = get_default_ha_automation_script()
        self.cache.set("ha_automation_script", default_ha_automation_script)

        return self.cache.get("ha_automation_script")

    def reset_user_pattern_prompt(self):
        """Reset the last prompt."""
        default_user_pattern_prompt = get_default_user_pattern_prompt()
        self.cache.set("user_pattern_prompt", default_user_pattern_prompt)

        return self.cache.get("user_pattern_prompt")
