import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

from redis.exceptions import RedisError
from sqlalchemy.exc import OperationalError

from src.application.services.dashboard_service import DashboardService
from src.application.services.statistics_refresh_service import StatisticsRefreshService
from src.core.batch_service_factory import build_batch_service
from src.core.config import settings
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.storage.dashboard_cache import DashboardCache
from src.storage.redis import create_redis_client
from src.tasks.celery_app import celery_app


async def _update_cached_statistics() -> dict[str, int]:
    today = datetime.now(ZoneInfo(settings.production_timezone)).date()
    client = create_redis_client()
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            service = StatisticsRefreshService(
                uow,
                build_batch_service(uow, client),
                DashboardService(
                    uow, DashboardCache(client, settings.dashboard_cache_ttl_seconds)
                ),
            )
            return await service.refresh_all(today=today)
    finally:
        try:
            await client.aclose()
        finally:
            await dispose_engine()


@celery_app.task(
    name="analytics.update_cached_statistics",
    autoretry_for=(OperationalError, RedisError),
    retry_backoff=True,
    max_retries=3,
)
def update_cached_statistics() -> dict[str, int]:
    return asyncio.run(_update_cached_statistics())
