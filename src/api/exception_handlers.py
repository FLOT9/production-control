from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchClosedError,
    BatchNotFoundError,
)
from src.domain.exceptions.product import (
    ProductAlreadyExistsError,
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
    ProductAlreadyExistsError: status.HTTP_409_CONFLICT,
    ProductNotFoundError: status.HTTP_404_NOT_FOUND,
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
