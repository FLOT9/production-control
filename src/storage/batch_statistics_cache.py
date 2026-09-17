import logging

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
    def _cache_key(batch_id: int) -> str:
        return f"batch-statistics:{batch_id}"

    async def get(self, batch_id: int) -> BatchStatistics | None:
        try:
            cached = await self.client.get(self._cache_key(batch_id))
        except RedisError:
            logger.warning(
                "Redis unavailable when reading statistics for Batch %s",
                batch_id,
                exc_info=True,
            )
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

    async def get_many(self, batch_ids: list[int]) -> dict[int, BatchStatistics]:
        if not batch_ids:
            return {}
        try:
            values = await self.client.mget(
                [self._cache_key(batch_id) for batch_id in batch_ids]
            )
        except RedisError:
            logger.warning(
                "Redis unavailable when reading batch statistics", exc_info=True
            )
            return {}
        found = {}
        for batch_id, value in zip(batch_ids, values, strict=True):
            statistics = self._decode(batch_id, value)
            if statistics is not None:
                found[batch_id] = statistics
        return found

    async def set_many(self, statistics: list[BatchStatistics]) -> None:
        if not statistics:
            return
        entries = [
            _BatchStatisticsCacheEntry.model_validate(item, from_attributes=True)
            for item in statistics
        ]
        try:
            async with self.client.pipeline(transaction=False) as pipeline:
                for entry in entries:
                    pipeline.set(
                        self._cache_key(entry.batch_id),
                        entry.model_dump_json(),
                        ex=self.ttl_seconds,
                    )
                await pipeline.execute()
        except RedisError:
            logger.warning(
                "Redis unavailable when caching batch statistics", exc_info=True
            )

    async def set(self, statistics: BatchStatistics) -> None:
        entry = _BatchStatisticsCacheEntry.model_validate(
            statistics,
            from_attributes=True,
        )
        try:
            await self.client.set(
                self._cache_key(statistics.batch_id),
                entry.model_dump_json(),
                ex=self.ttl_seconds,
            )
        except RedisError:
            logger.warning(
                "Redis unavailable when caching statistics for Batch %s",
                statistics.batch_id,
                exc_info=True,
            )

    async def delete(self, batch_id: int) -> None:
        try:
            await self.client.delete(self._cache_key(batch_id))
        except RedisError:
            logger.warning(
                "Failed to invalidate cached statistics for Batch %s",
                batch_id,
                exc_info=True,
            )
