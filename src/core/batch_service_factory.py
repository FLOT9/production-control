from redis.asyncio import Redis

from src.application.services.batch_service import BatchService
from src.application.services.webhook_event_service import WebhookEventService
from src.core.config import settings
from src.data.unit_of_work import UnitOfWork
from src.storage.batch_details_cache import BatchDetailsCache
from src.storage.batch_list_cache import BatchListCache
from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache


def build_batch_service(uow: UnitOfWork, redis_client: Redis) -> BatchService:
    return BatchService(
        uow=uow,
        statistics_cache=BatchStatisticsCache(
            redis_client, settings.batch_statistics_cache_ttl_seconds
        ),
        dashboard_cache=DashboardCache(
            redis_client, settings.dashboard_cache_ttl_seconds
        ),
        list_cache=BatchListCache(redis_client, settings.batch_list_cache_ttl_seconds),
        details_cache=BatchDetailsCache(
            redis_client, settings.batch_details_cache_ttl_seconds
        ),
        webhook_event_service=WebhookEventService(uow),
    )
