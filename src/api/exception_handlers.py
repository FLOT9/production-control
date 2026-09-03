from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchNotFoundError,
)
from src.domain.exceptions.work_center import (
    WorkCenterAlreadyExistsError,
    WorkCenterHasBatchesError,
    WorkCenterNotFoundError,
)


async def work_center_already_exists_handler(
    _request: Request,
    exc: WorkCenterAlreadyExistsError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def work_center_not_found_handler(
    _request: Request,
    exc: WorkCenterNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


async def work_center_has_batches_handler(
    _request: Request,
    exc: WorkCenterHasBatchesError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def batch_already_exists_handler(
    _request: Request,
    exc: BatchAlreadyExistsError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


async def batch_not_found_handler(
    _request: Request,
    exc: BatchNotFoundError,
) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": str(exc)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(
        WorkCenterAlreadyExistsError,
        work_center_already_exists_handler,
    )
    app.add_exception_handler(
        WorkCenterNotFoundError,
        work_center_not_found_handler,
    )
    app.add_exception_handler(
        WorkCenterHasBatchesError,
        work_center_has_batches_handler,
    )
    app.add_exception_handler(
        BatchAlreadyExistsError,
        batch_already_exists_handler,
    )
    app.add_exception_handler(
        BatchNotFoundError,
        batch_not_found_handler,
    )
