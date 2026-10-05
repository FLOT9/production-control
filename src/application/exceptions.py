from uuid import UUID


class BatchCsvHeadersError(Exception):
    def __init__(self, missing_headers: list[str]) -> None:
        headers = ", ".join(missing_headers)
        super().__init__(f"CSV is missing required headers: {headers}")


class BatchCsvFileError(Exception):
    """A file-level CSV error safe to return to the import client."""


class BatchExportFileError(Exception):
    """An expected export limitation safe to return to the client."""


class ProductionSummaryEmptyError(Exception):
    def __init__(
        self, message: str = "No production data available for report"
    ) -> None:
        super().__init__(message)


class ReportNotFoundError(Exception):
    def __init__(self, report_id: UUID) -> None:
        super().__init__(f"Report with id={report_id} was not found")


class ObjectStorageUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Object storage is unavailable")


class WebhookSubscriptionNotFoundError(Exception):
    def __init__(self, subscription_id: int) -> None:
        super().__init__(
            f"Webhook subscription with id={subscription_id} was not found"
        )


class WebhookDeliveryNotFoundError(Exception):
    def __init__(self, delivery_id: int) -> None:
        super().__init__(f"Webhook delivery with id={delivery_id} was not found")
