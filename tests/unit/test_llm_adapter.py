from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

import httpx
from gigachat.exceptions import GigaChatException
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel, ValidationError

from src.application.ai.exceptions import (
    AssistantTimeoutError,
    InvalidModelResponseError,
    LLMUnavailableError,
)
from src.integrations.llm.adapter import LangChainModelAdapter


class LLMAdapterTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.bound = Mock()
        self.bound.ainvoke = AsyncMock()
        model = Mock()
        model.bind_tools.return_value = self.bound
        self.adapter = LangChainModelAdapter(model, Mock())

    async def test_success_preserves_message(self):
        response = AIMessage(content="Ответ")
        self.bound.ainvoke.return_value = response
        self.assertIs(
            await self.adapter.ainvoke([HumanMessage(content="Вопрос")]), response
        )

    async def test_connection_and_sdk_errors_are_translated(self):
        for error in (
            httpx.ConnectError("private"),
            GigaChatException("private"),
            OSError("private"),
        ):
            with self.subTest(error=error):
                self.bound.ainvoke.side_effect = error
                with self.assertRaises(LLMUnavailableError) as raised:
                    await self.adapter.ainvoke([])
                self.assertNotIn("private", str(raised.exception))
                self.assertIs(raised.exception.__cause__, error)

    async def test_timeout_is_translated(self):
        self.bound.ainvoke.side_effect = httpx.ReadTimeout("private")
        with self.assertRaises(AssistantTimeoutError):
            await self.adapter.ainvoke([])

    async def test_provider_response_validation_is_translated(self):
        class ProviderResponse(BaseModel):
            value: int

        try:
            ProviderResponse.model_validate({"value": "invalid"})
        except ValidationError as error:
            self.bound.ainvoke.side_effect = error
        with self.assertRaises(InvalidModelResponseError):
            await self.adapter.ainvoke([])

    async def test_programming_errors_are_not_hidden(self):
        for error in (ValueError("bug"), TypeError("bug")):
            with self.subTest(error=error):
                self.bound.ainvoke.side_effect = error
                with self.assertRaises(type(error)) as raised:
                    await self.adapter.ainvoke([])
                self.assertIs(raised.exception, error)
