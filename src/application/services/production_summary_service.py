from asyncio import to_thread
from uuid import uuid4

from src.application.dto import StoredReport
from src.application.exceptions import ProductionSummaryEmptyError
from src.application.reports.production_summary_excel import (
    ProductionSummaryExcelGenerator,
)
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import ObjectStorage

REPORTS_BUCKET = "reports"
XLSX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class ProductionSummaryService:
    def __init__(
        self,
        uow: UnitOfWork,
        excel_generator: ProductionSummaryExcelGenerator,
        object_storage: ObjectStorage,
    ) -> None:
        self.uow = uow
        self.excel_generator = excel_generator
        self.object_storage = object_storage

    async def generate(self) -> bytes:
        rows = await self.uow.production_summaries.list_rows()

        if not rows:
            raise ProductionSummaryEmptyError()

        return await to_thread(self.excel_generator.generate, rows)

    async def generate_and_upload(self) -> StoredReport:
        data = await self.generate()

        report_id = uuid4()
        object_name = f"production-summary/{report_id}.xlsx"

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
