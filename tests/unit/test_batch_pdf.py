import re
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from src.application.reports.batch_pdf import BatchPdfGenerator
from src.application.services.batch_report_service import BatchReportService
from tests.unit.test_batch_details_cache import batch


class BatchPdfTests(IsolatedAsyncioTestCase):
    async def test_long_task_description_spans_multiple_pages(self):
        for repetitions in (100, 1000):
            with self.subTest(repetitions=repetitions):
                row = batch(is_closed=False)
                row.task_description = "Произвести детали по заданию. " * repetitions
                service = BatchReportService(
                    SimpleNamespace(
                        batches=SimpleNamespace(
                            get_with_products=AsyncMock(return_value=row)
                        )
                    )
                )
                report = await service.collect(42)
                data = BatchPdfGenerator("UTC").generate(report)
                self.assertTrue(data.startswith(b"%PDF"))
                self.assertTrue(data.rstrip().endswith(b"%%EOF"))
                self.assertGreater(len(re.findall(rb"/Type\s*/Page\b", data)), 1)
