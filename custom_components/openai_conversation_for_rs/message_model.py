"""Message models for the chat completion API"""

import json
import time
from typing import Any, List, Literal, Optional

from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from pydantic import BaseModel
from requests.models import Response


class BaseMessage(BaseModel):
    """Base message model"""

    id: Optional[int] = None
    role: str
    content: str

    def to_dict(self) -> dict:
        """Convert the message to a dictionary"""
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
        }


class UserMessage(BaseMessage):
    """User message model"""

    role: str = "user"
    content: str
    name: Optional[str] = None

    def to_dict(self) -> dict:
        ret = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
        }

        if self.name:
            ret["name"] = self.name

        return ret


class SystemMessage(BaseMessage):
    """System message model"""

    role: str = "system"
    content: str
    name: Optional[str] = None

    def to_dict(self) -> dict:
        ret = {
            "id": self.id,
            "role": self.role,
            "content": self.content,
        }

        if self.name:
            ret["name"] = self.name

        return ret


class ApiCall(BaseModel):
    """API call model"""

    method: Literal["get", "post", "delete"]
    endpoint: str
    body: dict = {}


class ApiCallFunction(Function):
    """API call function model"""

    arguments: ApiCall


class AssistantMessageToolCall(ChatCompletionMessageToolCall):
    """Assistant message tool call model"""

    function: ApiCallFunction


class AssistantMessage(BaseMessage):
    """Assistant message model"""

    role: str = "assistant"
    content: Optional[str] = None
    tool_calls: List[AssistantMessageToolCall] = []

    def __init__(self, /, **data: Any) -> None:
        if "tool_calls" in data:
            for tool_call in data["tool_calls"]:
                if isinstance(tool_call["function"]["arguments"], str):
                    api_call = json.loads(tool_call["function"]["arguments"])
                    api_call["endpoint"] = api_call["endpoint"].replace("{automation_id}", f"{time.time()}")
                    tool_call["function"]["arguments"] = api_call

        super().__init__(**data)

    def to_dict(self, to_str_arguments: bool = True) -> dict:
        ret = {
            "id": self.id,
            "role": self.role,
        }
        if self.content:
            ret["content"] = self.content

        tool_calls = []
        if self.tool_calls:
            for tool_call in self.tool_calls:
                tool_call_dict = tool_call.model_dump()

                if to_str_arguments:
                    arguments = tool_call.function.arguments.json(ensure_ascii=False)

                    tool_call_dict["function"] = {
                        "arguments": arguments,
                        "name": tool_call.function.name,
                    }

                tool_calls.append(tool_call_dict)

            ret["tool_calls"] = tool_calls

        return ret


class ToolMessage(BaseMessage):
    """Tool message model"""

    role: str = "tool"
    content: str
    tool_call_id: str

    @classmethod
    def from_api_response(cls, tool_call_id: str, response: Response):
        """Create a tool message from an API response"""
        return cls(
            content=json.dumps(
                {
                    "status_code": response.status_code,
                    "text": response.text,
                }
            ),
            tool_call_id=tool_call_id,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
        }
