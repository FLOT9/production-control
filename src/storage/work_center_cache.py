import logging
from datetime import datetime

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


class _WorkCenterCacheEntry(BaseModel):
    id: int
    identifier: str
    name: str
    created_at: datetime
    updated_at: datetime


class WorkCenterCache:
    def __init__(
        self,
        client: Redis,
        ttl_seconds: int,
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _cache_key(work_center_id: int) -> str:
        return f"work-center:{work_center_id}"

    async def get(
        self,
        work_center_id: int,
    ) -> dict[str, object] | None:
        try:
            cached = await self.client.get(
                self._cache_key(work_center_id),
            )
        except RedisError:
            logger.warning(
                "Redis unavailable when reading WorkCenter %s",
                work_center_id,
                exc_info=True,
            )
            return None

        if cached is None:
            return None

        try:
            entry = _WorkCenterCacheEntry.model_validate_json(cached)
        except ValidationError:
            logger.warning(
                "Invalid cached WorkCenter %s",
                work_center_id,
                exc_info=True,
            )
            return None

        return entry.model_dump(mode="json")

    async def set(
        self,
        work_center_id: int,
        data: dict[str, object],
    ) -> None:
        entry = _WorkCenterCacheEntry.model_validate(data)
        try:
            await self.client.set(
                self._cache_key(work_center_id),
                entry.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError:
            logger.warning(
                "Redis unavailable when caching WorkCenter %s",
                work_center_id,
                exc_info=True,
            )

    async def delete(self, work_center_id: int) -> None:
        try:
            await self.client.delete(
                self._cache_key(work_center_id),
            )
        except RedisError:
            logger.warning(
                "Failed to invalidate cache for deleted WorkCenter %s",
                work_center_id,
                exc_info=True,
            )
