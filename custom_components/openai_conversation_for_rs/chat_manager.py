"""Chat manager module."""

import logging
from typing import List

from .message_model import BaseMessage
from .prompt_manager import ClientCache

_LOGGER = logging.getLogger(__name__)


class ChatCache(ClientCache):
    """Chat cache."""

    def __init__(self, client_id):
        """Initialize the chat cache."""
        super().__init__(client_id)
        self.cache_key = "chat"

    def get_messages(self):
        """Get the messages."""
        messages = self.get(self.cache_key, [])
        _LOGGER.info("====================================")
        _LOGGER.info(f"{self.client_id} has messages: {len(messages)}")
        _LOGGER.info("====================================")
        return messages

    def _limit_messages(self, messages: List[BaseMessage], trigger_limit=20):
        """Limit the number of messages to 20."""
        while len(messages) > trigger_limit:
            if len(messages) and messages[0].role == "user":
                _LOGGER.debug(f"dropping message for limit. role: {messages[0].role}")
                messages.pop(0)

            while len(messages) and messages[0].role != "user":
                _LOGGER.debug(
                    f"dropping message for limit. role: {messages[0].role}")
                messages.pop(0)

        return messages

    def set_messages(self, value):
        """Set the messages."""
        processed_value = self._limit_messages(value)

        self.set(self.cache_key, processed_value)

    def reset_messages(self):
        """Reset the messages."""
        self.set(self.cache_key, [])


class ChatManager:
    """Chat manager."""

    def __init__(self, user_name):
        """Initialize the chat manager."""
        self.user_name = user_name
        self.chat_cache = ChatCache(user_name)

    def reset_messages(self):
        """Reset the messages."""
        self.chat_cache.reset_messages()

    @staticmethod
    def get_next_message_id(messages):
        """Get the next message id."""
        if not messages:
            return 0

        return messages[-1].id + 1

    def add_message(self, message: BaseMessage):
        """Add a message to the chat."""
        messages = self.chat_cache.get_messages()
        # TODO self.user_name 이 speaker_id 가 되어야 함..
        # _LOGGER.info("[%s] history %s", self.user_name, messages)
        message.id = self.get_next_message_id(messages)
        messages.append(message)
        self.chat_cache.set_messages(messages)

    def update_messages(self, messages):
        """Update the messages."""
        self.chat_cache.set_messages(messages)

    def get_messages(self):
        """Get the messages."""
        return self.chat_cache.get_messages()

    def get_dict_messages(self, tool_args_to_str=False):
        """Get the dict messages."""
        messages = self.get_messages()
        dict_messages = []

        for message in messages:
            if message.role == "assistant":
                dict_message = message.to_dict(to_str_arguments=tool_args_to_str)
            else:
                dict_message = message.to_dict()

            dict_messages.append(dict_message)

        return dict_messages

    def get_chat_input(self):
        """Get the chat input."""
        messages = self.chat_cache.get_messages()
        dict_messages = [message.to_dict() for message in messages]

        for message in dict_messages:
            message.pop("id")

        return dict_messages
