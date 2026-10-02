from asyncio import to_thread
from uuid import uuid4

from src.application.dto.report_format import ReportFormat, report_extension
from src.application.dto.stored_report import StoredReport
from src.application.reports.batch_excel import BatchExcelGenerator
from src.application.reports.batch_pdf import BatchPdfGenerator
from src.application.services.batch_report_service import BatchReportService
from src.storage.object_storage import ObjectStorage


class BatchReportFileService:
    def __init__(
        self,
        report_service: BatchReportService,
        object_storage: ObjectStorage,
        timezone: str,
    ) -> None:
        self.report_service = report_service
        self.object_storage = object_storage
        self.timezone = timezone

    async def generate_and_upload(
        self, batch_id: int, format: ReportFormat
    ) -> StoredReport:
        if format not in ("excel", "pdf"):
            raise ValueError("Unsupported report format")
        report_data = await self.report_service.collect(batch_id)
        # The DTO is independent from ORM objects; release the read transaction.
        await self.report_service.uow.rollback()
        generator = (
            BatchExcelGenerator(self.timezone)
            if format == "excel"
            else BatchPdfGenerator(self.timezone)
        )
        data = await to_thread(generator.generate, report_data)
        report_id = uuid4()
        object_name = f"batches/{batch_id}/{report_id}.{report_extension(format)}"
        content_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            if format == "excel"
            else "application/pdf"
        )
        await to_thread(
            self.object_storage.upload, "reports", object_name, data, content_type
        )
        return StoredReport(
            report_id=report_id, bucket="reports", object_name=object_name
        )
