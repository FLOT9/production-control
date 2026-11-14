import json
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_gigachat.chat_models.gigachat import _convert_message_to_dict
from pydantic import ValidationError

from src.application.ai.assistant_service import AssistantService
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
        self.assistant = AssistantService(model, tool)

    def request(self, *, name="get_batch_statistics", batch_id=1):
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": name,
                    "args": {"batch_id": batch_id},
                    "id": "call-1",
                    "type": "tool_call",
                }
            ],
        )

    async def test_tool_result_preserves_function_name_in_provider_payload(self):
        self.bound_model.ainvoke.side_effect = [
            self.request(),
            AIMessage(content="Осталось 2 изделия."),
        ]
        answer = await self.assistant.ask("Остаток партии с ID 1?")
        messages = self.bound_model.ainvoke.call_args_list[1].args[0]
        result_message = messages[-1]
        self.assertIsInstance(result_message, ToolMessage)
        self.assertEqual(result_message.tool_call_id, "call-1")
        # Проверяем реальный адаптер установленной версии, а не только ToolMessage.
        payload = _convert_message_to_dict(result_message).model_dump(mode="json")
        self.assertEqual(payload["role"], "function")
        self.assertEqual(payload["name"], "get_batch_statistics")
        self.assertEqual(json.loads(payload["content"])["remaining"], 2)
        self.assertIn("осталось 2", answer)
        self.read_statistics.assert_awaited_once_with(1)

    async def test_hallucinated_answer_without_tool_is_not_returned(self):
        self.bound_model.ainvoke.return_value = AIMessage(
            content="В партии с ID 1 осталось 999 изделий."
        )
        answer = await self.assistant.ask("Остаток партии с ID 1?")
        self.assertEqual(
            answer, "Недостаточно данных: модель не запросила статистику партии."
        )
        self.read_statistics.assert_not_awaited()
        self.assertEqual(self.bound_model.ainvoke.await_count, 1)

    async def test_final_hallucination_is_replaced_with_server_counts(self):
        self.bound_model.ainvoke.side_effect = [
            self.request(),
            AIMessage(content="Осталось 999 изделий, всего 1000."),
        ]
        answer = await self.assistant.ask("Остаток партии с ID 1?")
        self.assertEqual(
            answer, "Партия с ID 1: всего 10 изделий, агрегировано 8, осталось 2."
        )

    async def test_missing_batch_does_not_call_model_again(self):
        self.bound_model.ainvoke.return_value = self.request()
        self.read_statistics.side_effect = BatchNotFoundError(1)
        self.assertEqual(await self.assistant.ask("ID 1?"), "Партия не найдена.")
        self.assertEqual(self.bound_model.ainvoke.await_count, 1)

    async def test_unknown_tool_is_not_executed(self):
        self.bound_model.ainvoke.return_value = self.request(name="delete_batch")
        with self.assertRaisesRegex(ValueError, "Неизвестный инструмент"):
            await self.assistant.ask("ID 1?")
        self.read_statistics.assert_not_awaited()

    async def test_invalid_id_is_not_read(self):
        for batch_id in (0, -1, 2**31, True, "1"):
            with self.subTest(batch_id=batch_id):
                self.bound_model.ainvoke.return_value = self.request(batch_id=batch_id)
                with self.assertRaisesRegex(ValueError, "batch_id"):
                    await self.assistant.ask("Статистика?")
        self.read_statistics.assert_not_awaited()

    async def test_invalid_counts_are_not_sent_to_model(self):
        for result in (
            {"total": 10, "aggregated": 8, "remaining": -1},
            {"total": 10, "aggregated": 8, "remaining": 999},
            {"total": 10, "aggregated": 8, "remaining": "2"},
        ):
            with self.subTest(result=result):
                self.bound_model.ainvoke.reset_mock()
                self.bound_model.ainvoke.return_value = self.request()
                self.read_statistics.return_value = result
                with self.assertRaises(ValidationError):
                    await self.assistant.ask("ID 1?")
                self.assertEqual(self.bound_model.ainvoke.await_count, 1)
