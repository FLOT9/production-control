"""Short-lived dependencies for assistant tools."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.exceptions import RedisError
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from src.application.ai.exceptions import AssistantDataUnavailableError
from src.application.dto.analytics import BatchAnalyticsSnapshot
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.core.config import settings
from src.core.database import async_session_maker
from src.data.unit_of_work import UnitOfWork
from src.storage.analytics_cache import AnalyticsCache
from src.storage.redis import create_redis_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def batch_analytics_service() -> AsyncIterator[BatchAnalyticsService]:
    """Keep database and Redis resources within one tool execution."""
    redis = create_redis_client()
    failed = True
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
        failed = False
    except (
        OperationalError,
        InterfaceError,
        DisconnectionError,
        PoolTimeoutError,
        RedisError,
        OSError,
    ) as error:
        raise AssistantDataUnavailableError() from error
    finally:
        try:
            await redis.aclose()
        except (RedisError, OSError) as error:
            if not failed:
                raise AssistantDataUnavailableError() from error
            logger.warning(
                "Cannot close analytics cache client after a failed operation"
            )
