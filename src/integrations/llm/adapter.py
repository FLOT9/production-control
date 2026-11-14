import httpx
from gigachat.exceptions import GigaChatException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from src.application.ai.exceptions import (
    AssistantTimeoutError,
    InvalidModelResponseError,
    LLMUnavailableError,
)


class LangChainModelAdapter:
    """Translate provider failures into application exceptions."""

    def __init__(self, model: BaseChatModel, tool: BaseTool) -> None:
        self.model = model.bind_tools([tool])

    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage:
        try:
            return await self.model.ainvoke(messages)
        except httpx.TimeoutException as error:
            raise AssistantTimeoutError() from error
        except (httpx.HTTPError, GigaChatException, OSError) as error:
            raise LLMUnavailableError() from error
        except ValidationError as error:
            raise InvalidModelResponseError() from error
