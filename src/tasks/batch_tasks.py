import asyncio
from dataclasses import asdict
from datetime import date

from src.application.dto import BatchFilters
from src.application.exceptions import BatchCsvFileError, BatchCsvHeadersError
from src.application.importers import BatchCsvParser
from src.application.reports.batch_csv import BatchCsvExporter
from src.application.services.batch_export_service import BatchExportService
from src.application.services.batch_import_service import BatchImportService
from src.core.batch_service_factory import build_batch_service
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import create_object_storage
from src.storage.redis import create_redis_client
from src.tasks.celery_app import celery_app


async def _export_batches_csv(filters: BatchFilters) -> dict[str, str]:
    try:
        async with async_session_maker() as session:
            service = BatchExportService(
                uow=UnitOfWork(session),
                csv_exporter=BatchCsvExporter(),
                object_storage=create_object_storage(),
            )
            report = await service.export_and_upload_csv(filters=filters)
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
    filters = BatchFilters(
        is_closed=is_closed,
        batch_number=batch_number,
        batch_date=date.fromisoformat(batch_date) if batch_date else None,
        work_center_id=work_center_id,
        shift=shift,
    )
    return asyncio.run(_export_batches_csv(filters))


async def _import_batches_csv(object_name: str) -> dict:
    client = create_redis_client()
    try:
        storage = create_object_storage()
        data = await asyncio.to_thread(storage.download, "imports", object_name)
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            importer = BatchImportService(
                parser=BatchCsvParser(),
                batch_service=build_batch_service(uow, client),
            )
            try:
                result = await importer.import_csv(data)
            except BatchCsvHeadersError as error:
                raise BatchCsvFileError(str(error)) from error
            except UnicodeDecodeError as error:
                raise BatchCsvFileError("CSV must be UTF-8 encoded") from error
            return asdict(result)
    finally:
        try:
            await client.aclose()
        finally:
            await dispose_engine()


@celery_app.task(name="batches.import_csv")
def import_batches_csv(object_name: str) -> dict:
    return asyncio.run(_import_batches_csv(object_name))
