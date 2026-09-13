from typing import Annotated

from fastapi import Depends

from src.application.services.work_center_service import WorkCenterService
from src.core.config import settings
from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork
from src.storage.redis import redis_client
from src.storage.work_center_cache import WorkCenterCache


async def get_work_center_cache() -> WorkCenterCache:
    return WorkCenterCache(
        client=redis_client,
        ttl_seconds=settings.work_center_cache_ttl_seconds,
    )


async def get_work_center_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    cache: Annotated[WorkCenterCache, Depends(get_work_center_cache)],
) -> WorkCenterService:
    return WorkCenterService(uow, cache)


WorkCenterServiceDep = Annotated[
    WorkCenterService,
    Depends(get_work_center_service),
]
