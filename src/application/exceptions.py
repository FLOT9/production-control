from uuid import UUID


class ProductionSummaryEmptyError(Exception):
    def __init__(self) -> None:
        super().__init__("No production data available for report")


class ReportNotFoundError(Exception):
    def __init__(self, report_id: UUID) -> None:
        super().__init__(f"Report with id={report_id} was not found")


class ObjectStorageUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Object storage is unavailable")
