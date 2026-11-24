import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool

from src.application.ai.assistant_service import AssistantService
from src.application.ai.exceptions import (
    InvalidModelResponseError,
    InvalidToolResultError,
)
from src.application.ai.schemas import FindBatchesArgs
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
        self.read_search = AsyncMock(return_value={"items": [], "total": 0})

        async def find_batches(
            batch_number: int,
            batch_date=None,
            limit: int = 5,
            include_statistics: bool = False,
            **filters: object,
        ) -> dict:
            """Find batches by number."""
            return await self.read_search(batch_number, batch_date, limit)

        search_tool = StructuredTool.from_function(
            coroutine=find_batches, args_schema=FindBatchesArgs
        )
        self.assistant = AssistantService(self.bound_model, [tool, search_tool])

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

    def search_request(self, **args):
        return AIMessage(
            content="Найдена несуществующая партия 999",
            tool_calls=[
                {
                    "name": "find_batches",
                    "args": {"batch_number": 41, **args},
                    "id": "search-call",
                    "type": "tool_call",
                }
            ],
        )

    def found(self, batch_id=101, batch_date="2026-11-10"):
        return {
            "id": batch_id,
            "batch_number": 41,
            "batch_date": batch_date,
            "work_center_id": 7,
            "is_closed": False,
        }

    async def test_find_single_batch_returns_search_data_without_reading_statistics(
        self,
    ):
        self.bound_model.ainvoke.return_value = self.search_request()
        self.read_search.return_value = {"items": [self.found()], "total": 1}
        result = await self.assistant.ask("Найди партию №41")
        self.assertEqual(result.status, "answered")
        self.assertIn("ID 101", result.answer)
        self.assertNotIn("999", result.answer)
        self.assertIsNone(result.data)
        self.assertEqual(result.search.total, 1)
        self.assertEqual(result.tools_called, ["find_batches"])
        self.read_search.assert_awaited_once_with(41, None, 5)
        self.read_statistics.assert_not_awaited()
        self.assertEqual(self.bound_model.ainvoke.await_count, 1)

    async def test_find_missing_batch(self):
        self.bound_model.ainvoke.return_value = self.search_request()
        result = await self.assistant.ask("Найди партию №41")
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.search.items, [])
        self.assertEqual(result.search.total, 0)

    async def test_find_ambiguous_batch_uses_total_even_with_one_visible_item(self):
        self.bound_model.ainvoke.return_value = self.search_request(limit=1)
        self.read_search.return_value = {"items": [self.found()], "total": 12}
        result = await self.assistant.ask("Найди партию №41")
        self.assertEqual(result.status, "needs_clarification")
        self.assertIn("12", result.answer)
        self.assertIn("Уточните дату", result.answer)
        self.assertIn("Показаны первые 1", result.answer)
        self.assertIsNone(result.data)
        self.read_statistics.assert_not_awaited()

    async def test_statistics_by_number_requires_a_unique_batch(self):
        self.bound_model.ainvoke.return_value = self.search_request(
            limit=1, include_statistics=True
        )
        self.read_search.return_value = {"items": [self.found()], "total": 2}

        result = await self.assistant.ask("Сколько осталось в партии №41?")

        self.assertEqual(result.status, "needs_clarification")
        self.assertIsNone(result.data)
        self.assertEqual(result.tools_called, ["find_batches"])
        self.read_search.assert_awaited_once_with(41, None, 1)
        self.read_statistics.assert_not_awaited()
        self.assertEqual(self.bound_model.ainvoke.await_count, 1)

    async def test_unique_search_sends_its_result_to_the_model(self):
        first = self.search_request(include_statistics=True)
        self.bound_model.ainvoke.side_effect = [first, self.request(batch_id=101)]
        self.read_search.return_value = {"items": [self.found()], "total": 1}

        result = await self.assistant.ask("Сколько осталось в партии №41?")

        self.assertEqual(result.tools_called, ["find_batches", "get_batch_statistics"])
        self.assertEqual(self.bound_model.ainvoke.await_count, 2)
        original, follow_up = [
            call.args[0] for call in self.bound_model.ainvoke.await_args_list
        ]
        self.assertEqual(follow_up[:-2], original)
        self.assertIs(follow_up[-2], first)
        tool_message = follow_up[-1]
        self.assertIsInstance(tool_message, ToolMessage)
        self.assertEqual(tool_message.name, "find_batches")
        self.assertEqual(tool_message.tool_call_id, "search-call")
        self.assertEqual(json.loads(tool_message.content), {"batch_id": 101})
        self.read_statistics.assert_awaited_once_with(101)

    async def test_invalid_follow_up_uses_only_the_id_found_by_the_search(self):
        for follow_up in (
            self.request(batch_id=999),
            self.search_request(),
            AIMessage(content="Осталось 999 изделий."),
        ):
            with self.subTest(follow_up=follow_up):
                self.bound_model.ainvoke.reset_mock()
                self.read_statistics.reset_mock()
                self.bound_model.ainvoke.side_effect = [
                    self.search_request(include_statistics=True),
                    follow_up,
                ]
                self.read_search.return_value = {"items": [self.found()], "total": 1}

                result = await self.assistant.ask("Сколько осталось в партии №41?")

                self.assertIn("ID 101", result.answer)
                self.assertNotIn("999", result.answer)
                self.assertEqual(self.bound_model.ainvoke.await_count, 2)
                self.read_statistics.assert_awaited_once_with(101)

    async def test_find_valid_date_is_normalized_before_tool_execution(self):
        from datetime import date

        self.bound_model.ainvoke.return_value = self.search_request(
            batch_date="2026-11-10"
        )
        self.read_search.return_value = {"items": [self.found()], "total": 1}
        result = await self.assistant.ask("Найди №41 от 10 ноября 2026")
        self.assertEqual(result.status, "answered")
        self.read_search.assert_awaited_once_with(41, date(2026, 11, 10), 5)

    async def test_invalid_search_arguments_do_not_call_search(self):
        for args in (
            {"batch_number": True},
            {"batch_date": "wrong"},
            {"limit": 11},
            {"sql": "SELECT"},
        ):
            with self.subTest(args=args):
                self.bound_model.ainvoke.return_value = self.search_request(**args)
                with self.assertRaises(InvalidModelResponseError):
                    await self.assistant.ask("Найди №41")
        self.read_search.assert_not_awaited()

    async def test_inconsistent_search_results_are_rejected(self):
        for result in (
            {"items": [self.found()], "total": 0},
            {"items": [], "total": 1},
            {"items": [self.found(), self.found()], "total": 2},
            {"items": [{**self.found(), "batch_number": 42}], "total": 1},
            {"items": [self.found(batch_date="2026-11-09")], "total": 1},
        ):
            with self.subTest(result=result):
                self.bound_model.ainvoke.return_value = self.search_request(
                    batch_date="2026-11-10"
                )
                self.read_search.return_value = result
                with self.assertRaises(InvalidToolResultError):
                    await self.assistant.ask("Найди №41 от 10 ноября 2026")

    async def test_registry_rejects_duplicate_tool_names(self):
        tools = list(self.assistant.tools.values())
        with self.assertRaises(ValueError):
            AssistantService(self.bound_model, [tools[0], tools[0]])
