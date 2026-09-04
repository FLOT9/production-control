from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.api.v1.schemas import BatchCreate, BatchListResponse, BatchRead, BatchUpdate
from src.core.dependencies import get_batch_service
from src.domain.services.batch_service import BatchService

router = APIRouter(
    prefix="/batches",
    tags=["batches"],
)

BatchServiceDep = Annotated[
    BatchService,
    Depends(get_batch_service),
]


@router.post(
    "",
    response_model=BatchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch(
    payload: BatchCreate,
    service: BatchServiceDep,
) -> BatchRead:
    batch = await service.create(**payload.model_dump())
    return BatchRead.model_validate(batch)


@router.get(
    "/{batch_id}",
    response_model=BatchRead,
)
async def get_batch(
    batch_id: int,
    service: BatchServiceDep,
) -> BatchRead:
    batch = await service.get_by_id(batch_id)
    return BatchRead.model_validate(batch)


@router.patch(
    "/{batch_id}",
    response_model=BatchRead,
)
async def update_batch(
    batch_id: int,
    payload: BatchUpdate,
    service: BatchServiceDep,
) -> BatchRead:
    batch = await service.update_status(batch_id, payload.is_closed)
    return BatchRead.model_validate(batch)


@router.get(
    "",
    response_model=BatchListResponse,
)
async def list_batches(
    service: BatchServiceDep,
    is_closed: bool | None = None,
    batch_number: int | None = Query(None, gt=0),
    batch_date: date | None = None,
    work_center_id: int | None = Query(None, gt=0),
    shift: str | None = Query(None, min_length=1, max_length=50),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> BatchListResponse:
    batches, total = await service.list_batches(
        is_closed=is_closed,
        batch_number=batch_number,
        batch_date=batch_date,
        work_center_id=work_center_id,
        shift=shift,
        offset=offset,
        limit=limit,
    )

    result = BatchListResponse(
        items=[BatchRead.model_validate(batch) for batch in batches],
        total=total,
        offset=offset,
        limit=limit,
    )
    return result
