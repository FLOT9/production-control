import logging
from uuid import uuid4

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.application.dto import BatchStatistics

logger = logging.getLogger(__name__)


class _BatchStatisticsCacheEntry(BaseModel):
    batch_id: int
    total_products: int
    aggregated_products: int
    pending_products: int
    aggregation_percent: float


class BatchStatisticsCache:
    def __init__(
        self,
        client: Redis,
        ttl_seconds: int,
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _generation_key(batch_id: int) -> str:
        return f"batch-statistics:v2:{batch_id}:generation"

    async def make_key(self, batch_id: int) -> str | None:
        generation_key = self._generation_key(batch_id)
        try:
            generation = await self.client.get(generation_key)
            if generation is None:
                await self.client.set(generation_key, uuid4().hex, nx=True)
                generation = await self.client.get(generation_key)
            if generation is None:
                return None
            return f"batch-statistics:v2:{batch_id}:data:{generation}"
        except RedisError:
            logger.warning("Cannot read statistics cache generation", exc_info=True)
            return None

    async def make_keys(self, batch_ids: list[int]) -> dict[int, str | None]:
        return {batch_id: await self.make_key(batch_id) for batch_id in batch_ids}

    async def get(self, key: str | None, batch_id: int) -> BatchStatistics | None:
        if key is None:
            return None
        try:
            cached = await self.client.get(key)
        except RedisError:
            logger.warning("Cannot read statistics cache", exc_info=True)
            return None
        return self._decode(batch_id, cached)

    @staticmethod
    def _decode(batch_id: int, cached: str | None) -> BatchStatistics | None:
        if cached is None:
            return None

        try:
            entry = _BatchStatisticsCacheEntry.model_validate_json(cached)
        except ValidationError:
            logger.warning(
                "Invalid cached statistics for Batch %s",
                batch_id,
                exc_info=True,
            )
            return None

        if entry.batch_id != batch_id:
            logger.warning("Cached statistics ID mismatch for Batch %s", batch_id)
            return None
        return BatchStatistics(**entry.model_dump())

    async def get_many(self, keys: dict[int, str | None]) -> dict[int, BatchStatistics]:
        available = [(batch_id, key) for batch_id, key in keys.items() if key]
        if not available:
            return {}
        try:
            values = await self.client.mget([key for _, key in available])
        except RedisError:
            logger.warning(
                "Redis unavailable when reading batch statistics", exc_info=True
            )
            return {}
        found = {}
        for (batch_id, _), value in zip(available, values, strict=True):
            statistics = self._decode(batch_id, value)
            if statistics is not None:
                found[batch_id] = statistics
        return found

    async def set_many(
        self, keys: dict[int, str | None], statistics: list[BatchStatistics]
    ) -> None:
        if not statistics:
            return
        entries = [
            _BatchStatisticsCacheEntry.model_validate(item, from_attributes=True)
            for item in statistics
        ]
        try:
            async with self.client.pipeline(transaction=False) as pipeline:
                for entry in entries:
                    key = keys.get(entry.batch_id)
                    if key is not None:
                        pipeline.set(key, entry.model_dump_json(), ex=self.ttl_seconds)
                await pipeline.execute()
        except RedisError:
            logger.warning(
                "Redis unavailable when caching batch statistics", exc_info=True
            )

    async def set(self, key: str | None, statistics: BatchStatistics) -> None:
        if key is None:
            return
        entry = _BatchStatisticsCacheEntry.model_validate(
            statistics,
            from_attributes=True,
        )
        try:
            await self.client.set(
                key,
                entry.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError:
            logger.warning(
                "Redis unavailable when caching statistics for Batch %s",
                statistics.batch_id,
                exc_info=True,
            )

    async def invalidate(self, batch_id: int) -> None:
        try:
            await self.client.set(self._generation_key(batch_id), uuid4().hex)
        except RedisError:
            logger.warning(
                "Failed to invalidate cached statistics for Batch %s",
                batch_id,
                exc_info=True,
            )
