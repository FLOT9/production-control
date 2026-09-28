from datetime import date
from typing import Annotated

from fastapi import Depends, Query

from src.application.dto import BatchFilters
from src.application.services.batch_service import BatchService
from src.core.batch_service_factory import build_batch_service
from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork
from src.storage.redis import redis_client


def get_batch_filters(
    is_closed: bool | None = None,
    batch_number: int | None = Query(None, gt=0),
    batch_date: date | None = None,
    work_center_id: int | None = Query(None, gt=0),
    shift: str | None = Query(None, min_length=1, max_length=50),
) -> BatchFilters:
    return BatchFilters(
        is_closed=is_closed,
        batch_number=batch_number,
        batch_date=batch_date,
        work_center_id=work_center_id,
        shift=shift,
    )


BatchFiltersDep = Annotated[BatchFilters, Depends(get_batch_filters)]


async def get_batch_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchService:
    return build_batch_service(uow, redis_client)


BatchServiceDep = Annotated[
    BatchService,
    Depends(get_batch_service),
]
