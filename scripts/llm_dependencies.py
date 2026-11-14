"""Dependency setup for the local LLM learning script."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from src.application.dto.analytics import BatchAnalyticsSnapshot
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.core.config import settings
from src.core.database import async_session_maker
from src.data.unit_of_work import UnitOfWork
from src.storage.analytics_cache import AnalyticsCache
from src.storage.redis import create_redis_client


@asynccontextmanager
async def batch_analytics_service() -> AsyncIterator[BatchAnalyticsService]:
    """Keep database and Redis resources within one tool execution."""
    redis = create_redis_client()
    try:
        async with async_session_maker() as session:
            yield BatchAnalyticsService(
                UnitOfWork(session),
                AnalyticsCache(
                    redis,
                    BatchAnalyticsSnapshot,
                    settings.batch_statistics_cache_ttl_seconds,
                ),
            )
    finally:
        await redis.aclose()
