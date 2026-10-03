from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from src.application.services.batch_report_service import BatchReportService
from src.domain.exceptions.batch import BatchNotFoundError
from tests.unit.test_batch_details_cache import batch


class BatchReportServiceTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.row = batch(is_closed=False)
        self.uow = SimpleNamespace(
            batches=SimpleNamespace(get_with_products=AsyncMock(return_value=self.row)),
            commit=AsyncMock(),
        )
        self.service = BatchReportService(self.uow)

    async def test_empty_batch_has_zero_statistics(self):
        result = await self.service.collect(42)
        self.assertEqual(result.products, ())
        self.assertEqual(result.statistics.total_products, 0)
        self.assertEqual(result.statistics.aggregated_products, 0)
        self.assertEqual(result.statistics.pending_products, 0)
        self.assertEqual(result.statistics.aggregation_percent, 0)
        self.assertEqual(result.batch.batch_number, self.row.batch_number)
        self.uow.batches.get_with_products.assert_awaited_once_with(42)
        self.uow.commit.assert_not_awaited()

    async def test_counts_and_copies_products_into_independent_data(self):
        now = datetime.now(UTC)
        self.row.products = [
            SimpleNamespace(
                id=2,
                unique_code="P2",
                is_aggregated=False,
                aggregated_at=None,
                created_at=now,
            ),
            SimpleNamespace(
                id=1,
                unique_code="P1",
                is_aggregated=True,
                aggregated_at=now,
                created_at=now,
            ),
        ]
        result = await self.service.collect(42)
        self.assertEqual([p.id for p in result.products], [1, 2])
        self.assertEqual(result.statistics.total_products, 2)
        self.assertEqual(result.statistics.aggregated_products, 1)
        self.assertEqual(result.statistics.pending_products, 1)
        self.assertEqual(result.statistics.aggregation_percent, 50)
        self.assertEqual(result.products[0].aggregated_at, now)
        self.row.products[0].is_aggregated = True
        self.assertFalse(result.products[1].is_aggregated)
        self.assertEqual(result.generated_at.tzinfo, UTC)

    async def test_missing_batch_raises_domain_error(self):
        self.uow.batches.get_with_products.return_value = None
        with self.assertRaises(BatchNotFoundError):
            await self.service.collect(999)
