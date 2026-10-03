import asyncio
import csv
from dataclasses import asdict
from datetime import UTC, date, datetime
from typing import Literal

from celery import Task
from sqlalchemy.exc import OperationalError

from src.application.dto import BatchFilters
from src.application.events import WebhookEvent, WebhookEventType
from src.application.exceptions import BatchCsvFileError, BatchCsvHeadersError
from src.application.importers import BatchCsvParser
from src.application.importers.batch_excel import BatchExcelParser
from src.application.reports.batch_csv import BatchCsvExporter
from src.application.services.batch_export_service import BatchExportService
from src.application.services.batch_import_service import BatchImportService
from src.application.services.webhook_event_service import WebhookEventService
from src.core.batch_service_factory import build_batch_service
from src.core.config import settings
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import create_object_storage
from src.storage.redis import create_redis_client
from src.tasks.celery_app import celery_app


async def _auto_close_expired_batches() -> dict[str, int]:
    expired_before = datetime.now(UTC)
    client = create_redis_client()
    try:
        async with async_session_maker() as session:
            service = build_batch_service(UnitOfWork(session), client)
            return await service.close_expired_batches(expired_before=expired_before)
    finally:
        try:
            await client.aclose()
        finally:
            await dispose_engine()


@celery_app.task(
    name="batches.auto_close_expired",
    autoretry_for=(OperationalError,),
    retry_backoff=True,
    max_retries=3,
)
def auto_close_expired_batches() -> dict[str, int]:
    return asyncio.run(_auto_close_expired_batches())


async def _export_batches_csv(filters: BatchFilters) -> dict[str, str]:
    return await _export_batches(filters, "csv")


async def _export_batches(
    filters: BatchFilters, format: Literal["csv", "excel"]
) -> dict[str, str]:
    try:
        async with async_session_maker() as session:
            service = BatchExportService(
                uow=UnitOfWork(session),
                csv_exporter=BatchCsvExporter(),
                object_storage=create_object_storage(),
            )
            report = await service.export_and_upload(filters=filters, format=format)
            return {
                "report_id": str(report.report_id),
                "bucket": report.bucket,
                "object_name": report.object_name,
                "format": format,
                "download_url": f"{str(settings.public_api_url).rstrip('/')}/api/v1/batches/exports/{report.report_id}/download?format={format}",
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
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, str]:
    filters = BatchFilters(
        is_closed=is_closed,
        batch_number=batch_number,
        batch_date=date.fromisoformat(batch_date) if batch_date else None,
        work_center_id=work_center_id,
        shift=shift,
        date_from=date.fromisoformat(date_from) if date_from else None,
        date_to=date.fromisoformat(date_to) if date_to else None,
    )
    return asyncio.run(_export_batches_csv(filters))


async def _import_batches_csv(object_name: str, task_id: str | None = None) -> dict:
    return await _import_batches(object_name, "csv", task_id)


async def _import_batches(
    object_name: str, format: Literal["csv", "excel"], task_id: str | None = None
) -> dict:
    if format not in ("csv", "excel"):
        raise BatchCsvFileError("Unsupported import format")
    client = create_redis_client()
    try:
        storage = create_object_storage()
        data = await asyncio.to_thread(storage.download, "imports", object_name)
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            importer = BatchImportService(
                parser=BatchCsvParser() if format == "csv" else BatchExcelParser(),
                batch_service=build_batch_service(uow, client),
            )
            try:
                result = await importer.import_file(data)
            except BatchCsvHeadersError as error:
                raise BatchCsvFileError(str(error)) from error
            except UnicodeDecodeError as error:
                raise BatchCsvFileError("CSV must be UTF-8 encoded") from error
            except csv.Error as error:
                raise BatchCsvFileError("Invalid CSV file") from error
            await WebhookEventService(uow).create_deliveries(
                WebhookEvent(
                    WebhookEventType.IMPORT_COMPLETED,
                    {
                        "task_id": task_id,
                        "format": format,
                        "total": len(result.processed) + len(result.failed),
                        "imported": len(result.processed),
                        "failed": len(result.failed),
                        "batch_ids": [row.batch_id for row in result.processed],
                        "errors": [asdict(row) for row in result.failed],
                    },
                )
            )
            await uow.commit()
            return asdict(result)
    finally:
        try:
            await client.aclose()
        finally:
            await dispose_engine()


@celery_app.task(bind=True, name="batches.import_csv")
def import_batches_csv(self: Task, object_name: str) -> dict:
    return asyncio.run(_import_batches_csv(object_name, self.request.id))


@celery_app.task(bind=True, name="batches.import_file")
def import_batches_file(
    self: Task, object_name: str, format: Literal["csv", "excel"]
) -> dict:
    return asyncio.run(_import_batches(object_name, format, self.request.id))


@celery_app.task(name="batches.export_file")
def export_batches_file(
    format: Literal["csv", "excel"], filters: dict[str, object]
) -> dict[str, str]:
    values = dict(filters)
    for name in ("batch_date", "date_from", "date_to"):
        value = values.get(name)
        if isinstance(value, str):
            values[name] = date.fromisoformat(value)
    parsed = BatchFilters(**values)  # type: ignore[arg-type]  # API validates before JSON serialization.
    return asyncio.run(_export_batches(parsed, format))
