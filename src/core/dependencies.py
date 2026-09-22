from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.product_service import ProductService
from src.application.services.report_download_service import ReportDownloadService
from src.application.services.webhook_event_service import WebhookEventService
from src.core.config import settings
from src.core.database import get_db
from src.data.unit_of_work import UnitOfWork
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache
from src.storage.object_storage import create_object_storage
from src.storage.redis import redis_client


async def get_dashboard_cache() -> DashboardCache:
    return DashboardCache(redis_client, settings.dashboard_cache_ttl_seconds)


async def get_uow(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UnitOfWork:
    return UnitOfWork(session)


async def get_product_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    dashboard_cache: Annotated[DashboardCache, Depends(get_dashboard_cache)],
) -> ProductService:
    return ProductService(
        uow,
        BatchStatisticsCache(
            redis_client,
            settings.batch_statistics_cache_ttl_seconds,
        ),
        dashboard_cache,
        WebhookEventService(uow),
    )


async def get_report_download_service() -> ReportDownloadService:
    return ReportDownloadService(create_object_storage())
