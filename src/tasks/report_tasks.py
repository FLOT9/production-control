import asyncio
import logging

from celery import Task
from kombu.exceptions import KombuError

from src.application.dto.report_format import ReportFormat
from src.application.dto.stored_report import StoredReport
from src.application.events import WebhookEvent, WebhookEventType
from src.application.reports.production_summary_excel import (
    ProductionSummaryExcelGenerator,
)
from src.application.services.batch_report_file_service import BatchReportFileService
from src.application.services.batch_report_service import BatchReportService
from src.application.services.email_service import batch_report_download_url
from src.application.services.production_summary_service import (
    ProductionSummaryService,
)
from src.application.services.webhook_event_service import WebhookEventService
from src.core.config import settings
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.object_storage import create_object_storage
from src.tasks.celery_app import celery_app
from src.tasks.email_tasks import send_report_notification

logger = logging.getLogger(__name__)


async def _generate_production_summary(task_id: str | None = None) -> dict[str, str]:
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            excel_generator = ProductionSummaryExcelGenerator()
            object_storage = create_object_storage()

            service = ProductionSummaryService(
                uow=uow,
                excel_generator=excel_generator,
                object_storage=object_storage,
            )

            report = await service.generate_and_upload()
            await WebhookEventService(uow).create_deliveries(
                WebhookEvent(
                    WebhookEventType.REPORT_GENERATED,
                    {
                        "task_id": task_id,
                        "report_id": str(report.report_id),
                        "report_type": "production_summary",
                        "format": "excel",
                        "download_url": f"{str(settings.public_api_url).rstrip('/')}/api/v1/reports/{report.report_id}/download",
                    },
                )
            )
            await uow.commit()

            return {
                "report_id": str(report.report_id),
                "bucket": report.bucket,
                "object_name": report.object_name,
            }
    finally:
        await dispose_engine()


@celery_app.task(bind=True, name="reports.generate_production_summary")
def generate_production_summary(self: Task) -> dict[str, str]:
    return asyncio.run(_generate_production_summary(self.request.id))


async def _generate_batch_report(
    batch_id: int, format: ReportFormat, task_id: str | None = None
) -> StoredReport:
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            service = BatchReportFileService(
                BatchReportService(uow),
                create_object_storage(),
                settings.production_timezone,
            )
            report = await service.generate_and_upload(batch_id, format)
            await WebhookEventService(uow).create_deliveries(
                WebhookEvent(
                    WebhookEventType.REPORT_GENERATED,
                    {
                        "task_id": task_id,
                        "report_id": str(report.report_id),
                        "report_type": "batch",
                        "batch_id": batch_id,
                        "format": format,
                        "download_url": batch_report_download_url(
                            str(settings.public_api_url),
                            batch_id,
                            report.report_id,
                            format,
                        ),
                    },
                )
            )
            await uow.commit()
            return report
    finally:
        await dispose_engine()


@celery_app.task(bind=True, name="reports.generate_batch")
def generate_batch_report(
    self: Task, batch_id: int, format: ReportFormat = "excel", email: str | None = None
) -> dict[str, object]:
    report = asyncio.run(_generate_batch_report(batch_id, format, self.request.id))
    result: dict[str, object] = {
        "report_id": str(report.report_id),
        "batch_id": batch_id,
        "format": format,
        "download_url": batch_report_download_url(
            str(settings.public_api_url), batch_id, report.report_id, format
        ),
        "email_status": "not_requested",
        "email_task_id": None,
    }
    if email:
        try:
            task = send_report_notification.delay(
                email=email,
                batch_id=batch_id,
                report_id=str(report.report_id),
                format=format,
            )
        except (KombuError, OSError):
            logger.exception(
                "Cannot enqueue notification for report %s", report.report_id
            )
            result["email_status"] = "queue_failed"
        else:
            result["email_status"] = "queued"
            result["email_task_id"] = task.id
    return result
