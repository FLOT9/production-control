from typing import Literal

ReportFormat = Literal["excel", "pdf"]


def report_extension(format: ReportFormat) -> str:
    return "xlsx" if format == "excel" else "pdf"
