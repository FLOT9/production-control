from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.application.exceptions import (
    ObjectStorageUnavailableError,
    ReportNotFoundError,
    WebhookDeliveryNotFoundError,
    WebhookSubscriptionNotFoundError,
)
from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchClosedError,
    BatchComparisonInvalidError,
    BatchHasProductsError,
    BatchInvalidShiftPeriodError,
    BatchNotFoundError,
)
from src.domain.exceptions.product import (
    ProductAlreadyAggregatedError,
    ProductAlreadyExistsError,
    ProductBatchMismatchError,
    ProductNotFoundError,
)
from src.domain.exceptions.work_center import (
    WorkCenterAlreadyExistsError,
    WorkCenterHasBatchesError,
    WorkCenterNotFoundError,
)

ERROR_STATUS_CODES: dict[type[Exception], int] = {
    WorkCenterAlreadyExistsError: status.HTTP_409_CONFLICT,
    WorkCenterNotFoundError: status.HTTP_404_NOT_FOUND,
    WorkCenterHasBatchesError: status.HTTP_409_CONFLICT,
    BatchAlreadyExistsError: status.HTTP_409_CONFLICT,
    BatchNotFoundError: status.HTTP_404_NOT_FOUND,
    BatchClosedError: status.HTTP_409_CONFLICT,
    BatchComparisonInvalidError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    BatchHasProductsError: status.HTTP_409_CONFLICT,
    BatchInvalidShiftPeriodError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ProductAlreadyExistsError: status.HTTP_409_CONFLICT,
    ProductAlreadyAggregatedError: status.HTTP_409_CONFLICT,
    ProductBatchMismatchError: status.HTTP_409_CONFLICT,
    ProductNotFoundError: status.HTTP_404_NOT_FOUND,
    ReportNotFoundError: status.HTTP_404_NOT_FOUND,
    ObjectStorageUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    WebhookSubscriptionNotFoundError: status.HTTP_404_NOT_FOUND,
    WebhookDeliveryNotFoundError: status.HTTP_404_NOT_FOUND,
}


async def domain_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=ERROR_STATUS_CODES[type(exc)],
        content={"detail": str(exc)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    for error_type in ERROR_STATUS_CODES:
        app.add_exception_handler(error_type, domain_error_handler)
