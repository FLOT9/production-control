from asyncio import to_thread
from uuid import uuid4

from src.application.dto.stored_report import StoredReport
from src.application.reports.batch_excel import BatchExcelGenerator
from src.application.services.batch_report_service import BatchReportService
from src.storage.object_storage import ObjectStorage

REPORTS_BUCKET = "reports"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class BatchReportExcelService:
    def __init__(
        self,
        report_service: BatchReportService,
        excel_generator: BatchExcelGenerator,
        object_storage: ObjectStorage,
    ) -> None:
        self.report_service = report_service
        self.excel_generator = excel_generator
        self.object_storage = object_storage

    async def generate_and_upload(self, batch_id: int) -> StoredReport:
        report_data = await self.report_service.collect(batch_id)
        data = await to_thread(self.excel_generator.generate, report_data)

        report_id = uuid4()
        object_name = f"batches/{batch_id}/{report_id}.xlsx"

        await to_thread(
            self.object_storage.upload,
            REPORTS_BUCKET,
            object_name,
            data,
            XLSX_CONTENT_TYPE,
        )

        return StoredReport(
            report_id=report_id,
            bucket=REPORTS_BUCKET,
            object_name=object_name,
        )
