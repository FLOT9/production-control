import smtplib
import ssl
from email.message import EmailMessage
from uuid import UUID

from src.application.dto.report_format import ReportFormat
from src.core.config import Settings


def batch_report_download_url(
    base_url: str, batch_id: int, report_id: UUID, format: ReportFormat
) -> str:
    return f"{base_url.rstrip('/')}/api/v1/batches/{batch_id}/reports/{report_id}/download?format={format}"


class EmailService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send_report_notification(
        self, recipient: str, batch_id: int, report_id: UUID, format: ReportFormat
    ) -> None:
        url = batch_report_download_url(
            str(self.settings.public_api_url), batch_id, report_id, format
        )
        message = EmailMessage()
        message["From"] = self.settings.smtp_from_email
        message["To"] = recipient
        message["Subject"] = f"Отчёт по партии {batch_id} готов"
        message.set_content(
            f"Отчёт по партии {batch_id} в формате {format} готов.\n\nСкачать: {url}\n\nСсылка доступна, пока файл хранится в системе."
        )
        connection: smtplib.SMTP
        if self.settings.smtp_security == "ssl":
            connection = smtplib.SMTP_SSL(
                self.settings.smtp_host,
                self.settings.smtp_port,
                context=ssl.create_default_context(),
                timeout=self.settings.smtp_timeout_seconds,
            )
        else:
            connection = smtplib.SMTP(
                self.settings.smtp_host,
                self.settings.smtp_port,
                timeout=self.settings.smtp_timeout_seconds,
            )
        with connection as smtp:
            if self.settings.smtp_security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            if self.settings.smtp_username:
                password = (
                    self.settings.smtp_password.get_secret_value()
                    if self.settings.smtp_password
                    else ""
                )
                smtp.login(self.settings.smtp_username, password)
            smtp.send_message(message)
