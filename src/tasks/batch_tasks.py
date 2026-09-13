import asyncio
from datetime import date

from src.application.reports.batch_csv import BatchCsvExporter
from src.application.services.batch_export_service import BatchExportService
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import create_object_storage
from src.tasks.celery_app import celery_app


async def _export_batches_csv(
    *,
    is_closed: bool | None,
    batch_number: int | None,
    batch_date: str | None,
    work_center_id: int | None,
    shift: str | None,
) -> dict[str, str]:
    try:
        async with async_session_maker() as session:
            service = BatchExportService(
                uow=UnitOfWork(session),
                csv_exporter=BatchCsvExporter(),
                object_storage=create_object_storage(),
            )
            report = await service.export_and_upload_csv(
                is_closed=is_closed,
                batch_number=batch_number,
                batch_date=date.fromisoformat(batch_date) if batch_date else None,
                work_center_id=work_center_id,
                shift=shift,
            )
            return {
                "report_id": str(report.report_id),
                "bucket": report.bucket,
                "object_name": report.object_name,
            }
    finally:
        await dispose_engine()


@celery_app.task(name="batches.export_csv")
def export_batches_csv(
    *,
    is_closed: bool | None,
    batch_number: int | None,
    batch_date: str | None,
    work_center_id: int | None,
    shift: str | None,
) -> dict[str, str]:
    return asyncio.run(
        _export_batches_csv(
            is_closed=is_closed,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )
    )
