"""Generate prompts for the Home Assistant API"""

from typing import List

import yaml

from .message_model import SystemMessage
from .prompts.few_shot_prompts import tv_on_off_example


class PromptGenerator:
    """Generate prompts for the Home Assistant API"""

    def __init__(self, ha_contexts, services):
        self.ha_contexts = ha_contexts
        self.entities = ha_contexts["entities"]
        self.services = services

    def get_datetime_prompt(self):
        """Generate a prompt for the current date and time"""
        ha_time = self.ha_contexts["time"]
        ha_date = self.ha_contexts["date"]
        ha_weekday = self.ha_contexts["weekday"]

        base_prompt = f"""Current time is {ha_time}.
        Today's date is {ha_date}, and it's {ha_weekday} today.
        """

        return {
            "role": "system",
            "name": "now_datetime",
            "content": base_prompt,
        }

    def get_entities_system_prompt(self):
        """Generate a system prompt for the entities in the Home Assistant."""
        prompt = [
            "An overview of the states in this smart home:",
            yaml.dump(self.entities).encode("utf-8").decode("unicode_escape"),
        ]

        message = "\n".join(prompt)

        return {
            "role": "system",
            "name": "homeassistant_entities_overview",
            "content": message,
        }

    def get_services_system_prompt(self):
        """Generate a system prompt for the services in the Home Assistant."""
        prompt = [
            "An overview of the services in this smart home:",
            yaml.dump(self.services).encode("utf-8").decode("unicode_escape"),
        ]

        message = "\n".join(prompt)

        return {"role": "system", "name": "homeassistant_services_overview", "content": message}

    @staticmethod
    def get_tool():
        """Generate a tool for the Home Assistant API"""
        return {
            "type": "function",
            "function": {
                "name": "home_assistant_api",
                "description": "Home Assistant API",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["post", "get"]},
                        "endpoint": {"type": "string", "description": "The endpoint of the Home Assistant API"},
                        "body": {"type": "object", "description": "The body of the Home Assistant API"},
                    },
                    "required": ["method", "endpoint", "body"],
                    "additionalProperties": False,
                },
                "strict": False,
            },
        }


class GptHaAssistant:
    """GPT-based Home Assistant"""

    def __init__(
        self,
        deployment_name: str,
        init_prompt: str,
        ha_automation_script: str,
        user_pattern_prompt: str,
        tool_prompts: List[dict],
        client,
    ):
        self.init_prompt = init_prompt
        self.ha_automation_script = ha_automation_script
        self.user_pattern_prompt = user_pattern_prompt
        self.tool_prompts = tool_prompts
        self.deployment_name = deployment_name
        self.model_input_messages = []
        self.openai_client = client

    def add_instructions(self, chat_history: List[dict]):
        """Convert the chat history to JSON data"""
        model_input_messages = []
        if self.init_prompt:
            init_prompt_message = SystemMessage(content=self.init_prompt)
            model_input_messages.append(init_prompt_message.to_dict())
        if self.ha_automation_script:
            model_input_messages.append(SystemMessage(content=self.ha_automation_script).to_dict())
        if self.user_pattern_prompt:
            model_input_messages.append(SystemMessage(content=self.user_pattern_prompt).to_dict())
        model_input_messages.extend(tv_on_off_example)
        model_input_messages.extend(chat_history)

        return model_input_messages

    async def chat(self, chat_history: List[dict], n=1):
        """Chat with the GPT-based Home Assistant"""
        self.model_input_messages = self.add_instructions(chat_history)

        response = self.openai_client.chat.completions.create(
            model=self.deployment_name, messages=self.model_input_messages, tools=self.tool_prompts, n=n
        )

        return response
