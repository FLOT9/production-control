from typing import Annotated

from fastapi import APIRouter, Depends, status

from src.api.v1.schemas import BatchCreate, BatchRead, BatchUpdate
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
