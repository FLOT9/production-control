from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock
from uuid import UUID

from src.application.services.batch_report_excel_service import (
    XLSX_CONTENT_TYPE,
    BatchReportExcelService,
)
from src.domain.exceptions.batch import BatchNotFoundError


class BatchReportExcelServiceTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.report_data = object()
        self.collector = SimpleNamespace(
            collect=AsyncMock(return_value=self.report_data)
        )
        self.generator = SimpleNamespace(generate=Mock(return_value=b"excel-data"))
        self.storage = SimpleNamespace(upload=Mock())
        self.service = BatchReportExcelService(
            self.collector, self.generator, self.storage
        )

    async def test_uploads_file_before_returning_report(self) -> None:
        report = await self.service.generate_and_upload(42)
        self.collector.collect.assert_awaited_once_with(42)
        self.generator.generate.assert_called_once_with(self.report_data)
        self.assertIsInstance(report.report_id, UUID)
        self.assertEqual(report.bucket, "reports")
        self.assertEqual(report.object_name, f"batches/42/{report.report_id}.xlsx")
        self.storage.upload.assert_called_once_with(
            "reports", report.object_name, b"excel-data", XLSX_CONTENT_TYPE
        )

    async def test_upload_failure_propagates_instead_of_returning_success(self) -> None:
        self.storage.upload.side_effect = RuntimeError("MinIO unavailable")
        with self.assertRaisesRegex(RuntimeError, "MinIO unavailable"):
            await self.service.generate_and_upload(42)

    async def test_missing_batch_does_not_generate_or_upload(self) -> None:
        self.collector.collect.side_effect = BatchNotFoundError(42)
        with self.assertRaises(BatchNotFoundError):
            await self.service.generate_and_upload(42)
        self.generator.generate.assert_not_called()
        self.storage.upload.assert_not_called()

    async def test_generation_failure_does_not_upload(self) -> None:
        self.generator.generate.side_effect = RuntimeError("Generation failed")
        with self.assertRaisesRegex(RuntimeError, "Generation failed"):
            await self.service.generate_and_upload(42)
        self.storage.upload.assert_not_called()
