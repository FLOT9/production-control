from smtplib import SMTPException
from uuid import UUID

from src.application.dto.report_format import ReportFormat
from src.application.services.email_service import EmailService
from src.core.config import settings
from src.tasks.celery_app import celery_app


@celery_app.task(
    name="reports.send_notification",
    autoretry_for=(OSError, SMTPException),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def send_report_notification(
    email: str, batch_id: int, report_id: str, format: ReportFormat
) -> dict[str, str]:
    EmailService(settings).send_report_notification(
        email, batch_id, UUID(report_id), format
    )
    return {"email_status": "sent", "report_id": report_id}
