from datetime import date
from typing import Annotated

from fastapi import Depends, HTTPException, Query

from src.api.v1.schemas.common import OptionalPositiveInt32Query
from src.application.dto import BatchFilters
from src.application.services.batch_service import BatchService
from src.core.batch_service_factory import build_batch_service
from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork
from src.storage.redis import redis_client


def get_batch_filters(
    is_closed: bool | None = None,
    batch_number: OptionalPositiveInt32Query = None,
    batch_date: date | None = None,
    work_center_id: OptionalPositiveInt32Query = None,
    shift: str | None = Query(None, min_length=1, max_length=50),
    date_from: date | None = None,
    date_to: date | None = None,
) -> BatchFilters:
    try:
        return BatchFilters(
            is_closed=is_closed,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
            date_from=date_from,
            date_to=date_to,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


BatchFiltersDep = Annotated[BatchFilters, Depends(get_batch_filters)]


async def get_batch_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchService:
    return build_batch_service(uow, redis_client)


BatchServiceDep = Annotated[
    BatchService,
    Depends(get_batch_service),
]
