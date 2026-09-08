import json
import logging

from redis.asyncio import Redis
from redis.exceptions import RedisError

logger = logging.getLogger(__name__)


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

        return json.loads(cached)

    async def set(
        self,
        work_center_id: int,
        data: dict[str, object],
    ) -> None:
        try:
            await self.client.set(
                self._cache_key(work_center_id),
                json.dumps(data),
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
