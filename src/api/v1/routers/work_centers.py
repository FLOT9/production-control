from fastapi import APIRouter, status

from src.api.dependencies.work_centers import (
    WorkCenterServiceDep,
)
from src.api.v1.schemas import WorkCenterCreate, WorkCenterRead
from src.api.v1.schemas.common import PositiveInt32Path

router = APIRouter(
    prefix="/work-centers",
    tags=["work-centers"],
)


@router.post(
    "",
    response_model=WorkCenterRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_work_center(
    payload: WorkCenterCreate,
    service: WorkCenterServiceDep,
) -> WorkCenterRead:
    work_center = await service.create(payload.identifier, payload.name)
    return WorkCenterRead.model_validate(work_center)


@router.get(
    "/{work_center_id}",
    response_model=WorkCenterRead,
)
async def get_work_center(
    work_center_id: PositiveInt32Path,
    service: WorkCenterServiceDep,
) -> WorkCenterRead:
    work_center = await service.get_by_id(work_center_id)
    return WorkCenterRead.model_validate(work_center)


@router.delete(
    "/{work_center_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_work_center(
    work_center_id: PositiveInt32Path,
    service: WorkCenterServiceDep,
) -> None:
    await service.delete(work_center_id)
