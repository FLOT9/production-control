from pydantic import BaseModel, EmailStr

from src.application.dto.report_format import ReportFormat


class BatchReportRequest(BaseModel):
    format: ReportFormat = "excel"
    email: EmailStr | None = None
