"""Generate prompts for the Home Assistant API."""

import json
import logging
import traceback
from typing import List

import openai
import tiktoken
import yaml

from .message_model import SystemMessage

_LOGGER = logging.getLogger(__name__)


class PromptGenerator:
    """Generate prompts for the Home Assistant API."""

    def __init__(self, ha_contexts, services):
        """Initialize the prompt generator."""
        self.ha_contexts = ha_contexts
        self.entities = ha_contexts["entities"]
        self.services = services

    def get_datetime_prompt(self):
        """Generate a prompt for the current date and time."""
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
        """Generate a tool for the Home Assistant API."""
        return {
            "type": "function",
            "function": {
                "name": "home_assistant_api",
                "description": "Home Assistant API",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "enum": ["post", "get", "delete"]},
                        "endpoint": {"type": "string", "description": "The endpoint of the Home Assistant API"},
                        "body": {"type": "object", "description": "The body of the Home Assistant API"},
                    },
                    "required": ["method", "endpoint"],
                    "additionalProperties": False,
                },
                "strict": False,
            },
        }


class GptHaAssistant:
    """GPT-based Home Assistant."""

    def __init__(
        self,
        deployment_name: str,
        init_prompt: str,
        ha_automation_script: str,
        user_pattern_prompt: str,
        tool_prompts: list[dict],
        client,
    ):
        self.init_prompt = init_prompt
        self.ha_automation_script = ha_automation_script
        self.user_pattern_prompt = user_pattern_prompt
        self.tool_prompts = tool_prompts
        self.deployment_name = deployment_name
        self.model_input_messages = []
        self.openai_client = client

    def add_instructions(self, chat_history: list[dict]):
        """Convert the chat history to JSON data."""
        model_input_messages = []
        if self.init_prompt:
            init_prompt_message = SystemMessage(content=self.init_prompt)
            model_input_messages.append(init_prompt_message.to_dict())
        if self.user_pattern_prompt:
            model_input_messages.append(SystemMessage(content=self.user_pattern_prompt).to_dict())
        # model_input_messages.extend(tv_on_off_example)
        model_input_messages.extend(chat_history)

        return model_input_messages

    def crop_chat_history(self, chat_history: List[dict]):
        """Crop the chat history to the last 4 messages."""
        token_encoder = tiktoken.get_encoding("o200k_base")
        instructions_sum = self.init_prompt + self.ha_automation_script + self.user_pattern_prompt
        instructions_tokens = token_encoder.encode(instructions_sum)

        chat_history_tokens = token_encoder.encode(json.dumps(chat_history))
        while len(instructions_tokens) + len(chat_history_tokens) > 128000:
            for i, message in enumerate(chat_history[::-1], start=1):
                if message["role"] == "user":
                    chat_history = chat_history[: -(i + 3)]
            chat_history_tokens = token_encoder.encode(json.dumps(chat_history))
        return chat_history

    async def chat(self, chat_history: list[dict], n=1, temperature=0.5):
        """Chat with the GPT-based Home Assistant."""

        try:
            # _LOGGER.debug("Chat history: %s", chat_history)
            # cropped_chat_history = self.crop_chat_history(chat_history)
            self.model_input_messages = self.add_instructions(chat_history)

            response = await self.openai_client.chat.completions.create(
                model=self.deployment_name,
                messages=self.model_input_messages,
                tools=self.tool_prompts,
                n=n,
                temperature=temperature,
                seed=42
            )

        except openai.BadRequestError as err:
            return await self._handle_bad_request_error(err)

        except openai.RateLimitError:
            _LOGGER.warning("Rate limit exceeded")
            return self._create_error_response("Rate limit exceeded. Please try again later.")

        except openai.APIError as err:
            _LOGGER.error("Azure OpenAI API Error: %s", str(err))
            return self._create_error_response(f"API Error: {str(err)}")

        except Exception as err:
            _LOGGER.error("Unexpected error: %s", str(err))
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return self._create_error_response("An unknown error occurred. Please try again later.")

        return response

    def _create_error_response(self, message: str) -> dict:
        """Create a standardized error response."""
        return {
            "id": None,
            "object": "error",
            "created": None,
            "model": self.deployment_name,
            "choices": [],
            "error": {"message": message},
        }

    async def _handle_bad_request_error(self, err) -> str:
        """Handle BadRequestError and process content filtering results.

        Args:
            err (openai.BadRequestError): The error object

        Returns:
            str: Formatted error message for the user

        """
        default_message = "OpenAI가 명령을 이해하지 못했습니다. 다른 표현으로 다시 시도해주세요."
        error_data = None
        try:
            # 오류 데이터 파싱
            error_data = err.args[0]
            if not isinstance(error_data, str):
                _LOGGER.error("Unexpected error data type: %s", type(error_data))
                return default_message

            try:
                error_dict = json.loads(error_data)
                error_info = error_dict.get("error", {})
            except Exception:
                _LOGGER.error("Error data: %s", error_data)
                return default_message

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
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            return default_message

        except Exception:
            _LOGGER.error("Traceback: %s", traceback.format_exc())
            _LOGGER.error("Error response: %s", error_data)
            return default_message
