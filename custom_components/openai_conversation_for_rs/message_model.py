"""Message models for the chat completion API"""

import json
import time
from dataclasses import asdict, dataclass
from typing import Any, List, Literal, Optional

from openai.types.chat.chat_completion_message_tool_call import (
    ChatCompletionMessageToolCall,
    Function,
)
from requests.models import Response


@dataclass
class BaseMessage:
    """Base message model"""

    id: Optional[int] = None
    role: str = ""
    content: str = ""

    def to_dict(self) -> dict:
        """Convert the message to a dictionary"""
        return asdict(self)


@dataclass
class UserMessage(BaseMessage):
    """User message model"""

    role: str = "user"
    content: str = ""
    name: Optional[str] = None

    def to_dict(self) -> dict:
        ret = super().to_dict()
        if self.name:
            ret["name"] = self.name
        return ret


@dataclass
class SystemMessage(BaseMessage):
    """System message model"""

    role: str = "system"
    content: str = ""
    name: Optional[str] = None

    def to_dict(self) -> dict:
        ret = super().to_dict()
        if self.name:
            ret["name"] = self.name
        return ret


@dataclass
class ApiCall:
    """API call model"""

    method: Literal["get", "post"]
    endpoint: str
    body: dict


class ApiCallFunction(Function):
    """API call function model"""

    arguments: ApiCall


class AssistantMessageToolCall(ChatCompletionMessageToolCall):
    """Assistant message tool call model"""

    function: ApiCallFunction


@dataclass
class AssistantMessage(BaseMessage):
    """Assistant message model"""

    role: str = "assistant"
    content: Optional[str] = None
    tool_calls: List[AssistantMessageToolCall] = field(default_factory=list)

    def __init__(self, **data: Any) -> None:
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
                tool_call_dict = asdict(tool_call)

                if to_str_arguments:
                    arguments = json.dumps(asdict(tool_call.function.arguments))
                    tool_call_dict["function"] = {
                        "arguments": arguments,
                        "name": tool_call.function.arguments.endpoint,  # Replace with the correct name field
                    }

                tool_calls.append(tool_call_dict)

            ret["tool_calls"] = tool_calls

        return ret


@dataclass
class ToolMessage(BaseMessage):
    """Tool message model"""

    role: str = "tool"
    content: str = ""
    tool_call_id: str = ""

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
        ret = super().to_dict()
        ret["tool_call_id"] = self.tool_call_id
        return ret
