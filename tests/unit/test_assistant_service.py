from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import StructuredTool

from src.application.ai.assistant_service import AssistantService
from src.application.ai.exceptions import (
    InvalidModelResponseError,
    InvalidToolResultError,
)
from src.domain.exceptions.batch import BatchNotFoundError


class AssistantServiceTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.read_statistics = AsyncMock(
            return_value={"total": 10, "aggregated": 8, "remaining": 2}
        )

        async def get_batch_statistics(batch_id: int) -> dict[str, int]:
            """Получить статистику партии по ID."""
            return await self.read_statistics(batch_id)

        tool = StructuredTool.from_function(coroutine=get_batch_statistics)
        self.bound_model = Mock()
        self.bound_model.ainvoke = AsyncMock()
        model = Mock(spec=BaseChatModel)
        model.bind_tools.return_value = self.bound_model
        self.assistant = AssistantService(self.bound_model, tool)

    def request(self, *, name="get_batch_statistics", batch_id=1):
        return AIMessage(
            content="Осталось 999 изделий.",
            tool_calls=[
                {
                    "name": name,
                    "args": {"batch_id": batch_id},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )

    async def test_success_uses_server_counts_and_only_one_model_call(self):
        self.bound_model.ainvoke.return_value = self.request()
        result = await self.assistant.ask("ID 1?")
        self.assertEqual(result.status, "answered")
        self.assertEqual(
            result.answer,
            "Партия с ID 1: всего 10 изделий, агрегировано 8, осталось 2.",
        )
        self.assertEqual(
            result.data.model_dump(),
            {"batch_id": 1, "total": 10, "aggregated": 8, "remaining": 2},
        )
        self.assertEqual(result.tools_called, ["get_batch_statistics"])
        self.read_statistics.assert_awaited_once_with(1)
        self.assertEqual(self.bound_model.ainvoke.await_count, 1)

    async def test_hallucination_without_tool_is_not_returned(self):
        self.bound_model.ainvoke.return_value = AIMessage(
            content="Осталось 999 изделий."
        )
        result = await self.assistant.ask("ID 1?")
        self.assertEqual(result.status, "insufficient_data")
        self.assertNotIn("999", result.answer)
        self.assertIsNone(result.data)
        self.assertEqual(result.tools_called, [])
        self.read_statistics.assert_not_awaited()

    async def test_missing_batch(self):
        self.bound_model.ainvoke.return_value = self.request()
        self.read_statistics.side_effect = BatchNotFoundError(1)
        result = await self.assistant.ask("ID 1?")
        self.assertEqual(result.status, "not_found")
        self.assertIsNone(result.data)
        self.assertEqual(result.tools_called, ["get_batch_statistics"])

    async def test_unknown_tool_is_not_executed(self):
        self.bound_model.ainvoke.return_value = self.request(name="delete_batch")
        with self.assertRaises(InvalidModelResponseError):
            await self.assistant.ask("ID 1?")
        self.read_statistics.assert_not_awaited()

    async def test_multiple_tools_are_not_executed(self):
        response = self.request()
        response.tool_calls.append(dict(response.tool_calls[0], id="call-2"))
        self.bound_model.ainvoke.return_value = response
        with self.assertRaises(InvalidModelResponseError):
            await self.assistant.ask("ID 1?")
        self.read_statistics.assert_not_awaited()

    async def test_invalid_id_is_not_read(self):
        for batch_id in (0, -1, 2**31, True, "1"):
            with self.subTest(batch_id=batch_id):
                self.bound_model.ainvoke.return_value = self.request(batch_id=batch_id)
                with self.assertRaises(InvalidModelResponseError):
                    await self.assistant.ask("Статистика?")
        self.read_statistics.assert_not_awaited()

    async def test_invalid_counts_are_rejected(self):
        for remaining in (-1, 999, "2"):
            with self.subTest(remaining=remaining):
                self.bound_model.ainvoke.return_value = self.request()
                self.read_statistics.return_value = {
                    "total": 10,
                    "aggregated": 8,
                    "remaining": remaining,
                }
                with self.assertRaises(InvalidToolResultError):
                    await self.assistant.ask("ID 1?")
