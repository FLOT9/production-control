from typing import Annotated

from fastapi import Depends

from src.application.services.batch_service import BatchService
from src.core.config import settings
from src.core.dependencies import get_dashboard_cache, get_uow
from src.data.unit_of_work import UnitOfWork
from src.storage.batch_details_cache import BatchDetailsCache
from src.storage.batch_list_cache import BatchListCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache
from src.storage.redis import redis_client


async def get_batch_statistics_cache() -> BatchStatisticsCache:
    return BatchStatisticsCache(
        client=redis_client,
        ttl_seconds=settings.batch_statistics_cache_ttl_seconds,
    )


async def get_batch_list_cache() -> BatchListCache:
    return BatchListCache(redis_client, settings.batch_list_cache_ttl_seconds)


async def get_batch_details_cache() -> BatchDetailsCache:
    return BatchDetailsCache(redis_client, settings.batch_details_cache_ttl_seconds)


async def get_batch_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    dashboard_cache: Annotated[DashboardCache, Depends(get_dashboard_cache)],
    list_cache: Annotated[BatchListCache, Depends(get_batch_list_cache)],
    details_cache: Annotated[BatchDetailsCache, Depends(get_batch_details_cache)],
    statistics_cache: Annotated[
        BatchStatisticsCache,
        Depends(get_batch_statistics_cache),
    ],
) -> BatchService:
    return BatchService(
        uow, statistics_cache, dashboard_cache, list_cache, details_cache
    )


BatchServiceDep = Annotated[
    BatchService,
    Depends(get_batch_service),
]
