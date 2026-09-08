from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.work_center_command_service import (
    WorkCenterCommandService,
)
from src.application.services.work_center_query_service import WorkCenterQueryService
from src.core.config import settings
from src.core.database import get_db
from src.data.unit_of_work import UnitOfWork
from src.domain.services.batch_service import BatchService
from src.domain.services.product_service import ProductService
from src.domain.services.work_center_service import WorkCenterService
from src.storage.redis import redis_client
from src.storage.work_center_cache import WorkCenterCache


async def get_uow(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UnitOfWork:
    return UnitOfWork(session)


async def get_work_center_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> WorkCenterService:
    return WorkCenterService(uow)


async def get_batch_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchService:
    return BatchService(uow)


async def get_product_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> ProductService:
    return ProductService(uow)


async def get_work_center_cache() -> WorkCenterCache:
    return WorkCenterCache(
        client=redis_client,
        ttl_seconds=settings.work_center_cache_ttl_seconds,
    )


async def get_work_center_query_service(
    work_center_service: Annotated[
        WorkCenterService,
        Depends(get_work_center_service),
    ],
    cache: Annotated[
        WorkCenterCache,
        Depends(get_work_center_cache),
    ],
) -> WorkCenterQueryService:
    return WorkCenterQueryService(
        work_center_service=work_center_service,
        cache=cache,
    )


async def get_work_center_command_service(
    work_center_service: Annotated[
        WorkCenterService,
        Depends(get_work_center_service),
    ],
    cache: Annotated[
        WorkCenterCache,
        Depends(get_work_center_cache),
    ],
) -> WorkCenterCommandService:
    return WorkCenterCommandService(
        work_center_service=work_center_service,
        cache=cache,
    )
