from contextlib import asynccontextmanager
from datetime import date
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from pydantic import ValidationError

from src.application.ai.tools import create_find_batches_tool


class FindBatchesToolTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.opened = False
        self.closed = False
        self.service = SimpleNamespace(list_batches=AsyncMock())

        @asynccontextmanager
        async def service_factory():
            self.opened = True
            try:
                yield self.service
            finally:
                self.closed = True

        self.tool = create_find_batches_tool(service_factory)

    async def test_search_filters_projection_and_resource_scope(self):
        row = {
            "id": 101,
            "batch_number": 41,
            "batch_date": date(2026, 11, 10),
            "work_center_id": 7,
            "is_closed": False,
            "task_description": "private",
        }
        for source in (row, SimpleNamespace(**row)):
            with self.subTest(source=type(source).__name__):
                self.service.list_batches.return_value = ([source], 12)
                result = await self.tool.ainvoke(
                    {"batch_number": 41, "batch_date": "2026-11-10", "limit": 5}
                )
                self.assertEqual(
                    result,
                    {
                        "items": [
                            {
                                "id": 101,
                                "batch_number": 41,
                                "batch_date": "2026-11-10",
                                "work_center_id": 7,
                                "is_closed": False,
                            }
                        ],
                        "total": 12,
                    },
                )
                kwargs = self.service.list_batches.call_args.kwargs
                self.assertEqual(kwargs["filters"].batch_number, 41)
                self.assertEqual(kwargs["filters"].batch_date, date(2026, 11, 10))
                self.assertEqual((kwargs["offset"], kwargs["limit"]), (0, 5))
                self.assertTrue(self.opened and self.closed)

    async def test_empty_result_and_default_arguments(self):
        self.service.list_batches.return_value = ([], 0)
        self.assertEqual(
            await self.tool.ainvoke({"batch_number": 41}), {"items": [], "total": 0}
        )
        kwargs = self.service.list_batches.call_args.kwargs
        self.assertIsNone(kwargs["filters"].batch_date)
        self.assertEqual(kwargs["limit"], 5)

    async def test_invalid_arguments_do_not_open_service(self):
        for args in (
            {"batch_number": 0},
            {"batch_number": True},
            {"batch_number": 41, "limit": 11},
            {"batch_number": 41, "service": "injected"},
        ):
            with self.subTest(args=args), self.assertRaises(ValidationError):
                await self.tool.ainvoke(args)
        self.assertFalse(self.opened)
        self.service.list_batches.assert_not_awaited()
        self.assertEqual(self.tool.name, "find_batches")
        self.assertNotIn(
            "service", self.tool.get_input_schema().model_json_schema()["properties"]
        )

    async def test_service_failure_closes_context(self):
        self.service.list_batches.side_effect = RuntimeError("failure")
        with self.assertRaisesRegex(RuntimeError, "failure"):
            await self.tool.ainvoke({"batch_number": 41})
        self.assertTrue(self.closed)
