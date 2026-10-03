from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from redis.exceptions import ConnectionError

from src.application.services.product_service import ProductService
from src.domain.exceptions.batch import BatchClosedError, BatchNotFoundError
from src.domain.exceptions.product import (
    ProductAlreadyAggregatedError,
    ProductBatchMismatchError,
    ProductNotFoundError,
)


class ProductAggregateManyTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.uow = SimpleNamespace(rollback=AsyncMock())
        self.service = ProductService(
            self.uow, AsyncMock(), AsyncMock(), AsyncMock(), AsyncMock()
        )
        self.service.aggregate = AsyncMock()

    async def test_domain_error_rolls_back_before_next_product(self) -> None:
        for error in (
            ProductNotFoundError("P2"),
            ProductBatchMismatchError("P2", 42, 99),
            ProductAlreadyAggregatedError("P2"),
            BatchClosedError(42),
            BatchNotFoundError(42),
        ):
            with self.subTest(error=error):
                self.uow.rollback.reset_mock()
                calls = []

                async def aggregate(*, unique_code, batch_id, error=error, calls=calls):
                    self.assertEqual(batch_id, 42)
                    if unique_code == "P3":
                        self.uow.rollback.assert_awaited_once()
                    calls.append(unique_code)
                    if unique_code == "P2":
                        raise error

                self.service.aggregate.side_effect = aggregate
                result = await self.service.aggregate_many(
                    batch_id=42, unique_codes=["P1", "P2", "P3"]
                )
                self.assertEqual(calls, ["P1", "P2", "P3"])
                self.assertFalse(result["success"])
                self.assertEqual(result["total"], 3)
                self.assertEqual(result["aggregated"], 2)
                self.assertEqual(result["failed"], 1)
                self.assertEqual(
                    result["errors"], [{"unique_code": "P2", "reason": str(error)}]
                )

    async def test_system_error_stops_processing_and_propagates(self) -> None:
        self.service.aggregate.side_effect = [None, RuntimeError("DB unavailable")]
        with self.assertRaisesRegex(RuntimeError, "DB unavailable"):
            await self.service.aggregate_many(
                batch_id=42, unique_codes=["P1", "P2", "P3"]
            )
        self.assertEqual(self.service.aggregate.await_count, 2)

    async def test_all_successful(self) -> None:
        result = await self.service.aggregate_many(
            batch_id=42, unique_codes=["P1", "P2"]
        )
        self.assertEqual(
            result,
            {"success": True, "total": 2, "aggregated": 2, "failed": 0, "errors": []},
        )
        self.uow.rollback.assert_not_awaited()

    async def test_progress_counts_successes_and_expected_errors(self) -> None:
        progress = AsyncMock()
        self.service.aggregate.side_effect = [None, ProductNotFoundError("P2"), None]
        await self.service.aggregate_many(
            batch_id=42, unique_codes=["P1", "P2", "P3"], on_progress=progress
        )
        self.assertEqual(
            [call.args for call in progress.await_args_list],
            [(1, 3), (2, 3), (3, 3)],
        )

    async def test_system_error_does_not_publish_completed_progress(self) -> None:
        progress = AsyncMock()
        self.service.aggregate.side_effect = [None, RuntimeError("DB unavailable")]
        with self.assertRaises(RuntimeError):
            await self.service.aggregate_many(
                batch_id=42, unique_codes=["P1", "P2", "P3"], on_progress=progress
            )
        progress.assert_awaited_once_with(1, 3)

    async def test_progress_failure_does_not_interrupt_product_processing(self) -> None:
        progress = AsyncMock(
            side_effect=[ConnectionError("Redis unavailable"), None, None]
        )
        self.service.aggregate.side_effect = [None, ProductNotFoundError("P2"), None]
        with self.assertLogs(
            "src.application.services.product_service", level="WARNING"
        ) as logs:
            result = await self.service.aggregate_many(
                batch_id=42, unique_codes=["P1", "P2", "P3"], on_progress=progress
            )

        self.assertEqual(self.service.aggregate.await_count, 3)
        self.assertEqual(result["aggregated"], 2)
        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["errors"][0]["unique_code"], "P2")
        self.uow.rollback.assert_awaited_once()
        self.assertEqual(
            [call.args for call in progress.await_args_list], [(1, 3), (2, 3), (3, 3)]
        )
        self.assertIn("progress", logs.output[0])
