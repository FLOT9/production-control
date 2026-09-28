from asyncio import to_thread
from uuid import uuid4

from src.application.dto import BatchFilters, StoredReport
from src.application.reports.batch_csv import BatchCsvExporter
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import ObjectStorage

REPORTS_BUCKET = "reports"
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

    async def export_and_upload_csv(
        self,
        *,
        filters: BatchFilters,
    ) -> StoredReport:
        batches = await self.uow.batches.list_for_export(filters=filters)
        data = await to_thread(self.csv_exporter.generate, batches)

        report_id = uuid4()
        object_name = f"batch-exports/{report_id}.csv"
        await to_thread(
            self.object_storage.upload,
            REPORTS_BUCKET,
            object_name,
            data,
            CSV_CONTENT_TYPE,
        )

        return StoredReport(
            report_id=report_id,
            bucket=REPORTS_BUCKET,
            object_name=object_name,
        )
