from asyncio import to_thread
from typing import Literal
from uuid import uuid4

from src.application.dto import BatchFilters, StoredReport
from src.application.reports.batch_csv import BatchCsvExporter
from src.application.reports.batch_excel_export import BatchExcelExporter
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import ObjectStorage

EXPORTS_BUCKET = "exports"
CSV_CONTENT_TYPE = "text/csv; charset=utf-8"


class BatchExportService:
    def __init__(
        self,
        uow: UnitOfWork,
        csv_exporter: BatchCsvExporter,
        object_storage: ObjectStorage,
    ) -> None:
        self.uow = uow
        self.csv_exporter = csv_exporter
        self.object_storage = object_storage

    async def export_and_upload_csv(self, *, filters: BatchFilters) -> StoredReport:
        return await self.export_and_upload(filters=filters, format="csv")

    async def export_and_upload(
        self, *, filters: BatchFilters, format: Literal["csv", "excel"]
    ) -> StoredReport:
        if format not in ("csv", "excel"):
            raise ValueError("Unsupported export format")
        batches = await self.uow.batches.list_for_export(filters=filters)
        # Generators only use loaded scalar fields. Release SQL transaction after serialization.
        generator = self.csv_exporter if format == "csv" else BatchExcelExporter()
        data = await to_thread(generator.generate, batches)
        await self.uow.rollback()
        report_id = uuid4()
        extension = "csv" if format == "csv" else "xlsx"
        object_name = f"batch-exports/{report_id}.{extension}"
        content_type = (
            CSV_CONTENT_TYPE
            if format == "csv"
            else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        await to_thread(
            self.object_storage.upload, EXPORTS_BUCKET, object_name, data, content_type
        )
        return StoredReport(
            report_id=report_id, bucket=EXPORTS_BUCKET, object_name=object_name
        )
