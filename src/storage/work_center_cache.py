import logging
from datetime import datetime
from uuid import uuid4

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
    def _generation_key(work_center_id: int) -> str:
        return f"work-center:v2:{work_center_id}:generation"

    async def make_key(self, work_center_id: int) -> str | None:
        generation_key = self._generation_key(work_center_id)
        try:
            generation = await self.client.get(generation_key)
            if generation is None:
                await self.client.set(generation_key, uuid4().hex, nx=True)
                generation = await self.client.get(generation_key)
            if generation is None:
                return None
            return f"work-center:v2:{work_center_id}:data:{generation}"
        except RedisError:
            logger.warning("Cannot read WorkCenter cache generation", exc_info=True)
            return None

    async def get(
        self,
        key: str | None,
        work_center_id: int,
    ) -> dict[str, object] | None:
        if key is None:
            return None
        try:
            cached = await self.client.get(key)
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

        if entry.id != work_center_id:
            logger.warning("Cached WorkCenter ID mismatch for %s", work_center_id)
            return None

        return entry.model_dump(mode="json")

    async def set(
        self,
        key: str | None,
        work_center_id: int,
        data: dict[str, object],
    ) -> None:
        if key is None:
            return
        entry = _WorkCenterCacheEntry.model_validate(data)
        try:
            await self.client.set(
                key,
                entry.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError:
            logger.warning(
                "Redis unavailable when caching WorkCenter %s",
                work_center_id,
                exc_info=True,
            )

    async def invalidate(self, work_center_id: int) -> None:
        try:
            await self.client.set(self._generation_key(work_center_id), uuid4().hex)
        except RedisError:
            logger.warning(
                "Failed to invalidate cache for deleted WorkCenter %s",
                work_center_id,
                exc_info=True,
            )
