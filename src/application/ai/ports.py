from typing import Protocol

from langchain_core.messages import BaseMessage


class AssistantModel(Protocol):
    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage: ...
