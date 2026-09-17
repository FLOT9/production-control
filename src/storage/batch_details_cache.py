import logging

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.data.models import Batch
from src.storage.batch_list_cache import _BatchEntry

logger = logging.getLogger(__name__)


class BatchDetailsCache:
    def __init__(
        self, client: Redis, ttl_seconds: int, prefix: str = "batch-details"
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    def _cache_key(self, batch_id: int) -> str:
        return f"{self.prefix}:{batch_id}"

    async def get(self, batch_id: int) -> dict[str, object] | None:
        try:
            value = await self.client.get(self._cache_key(batch_id))
            if value is None:
                return None
            entry = _BatchEntry.model_validate_json(value)
            if entry.id != batch_id:
                logger.warning("Cached batch ID mismatch for %s", batch_id)
                return None
            return entry.model_dump()
        except (RedisError, ValidationError):
            logger.warning("Cannot read batch details cache", exc_info=True)
            return None

    async def set(self, batch: Batch) -> None:
        entry = _BatchEntry.model_validate(batch)
        try:
            await self.client.set(
                self._cache_key(batch.id), entry.model_dump_json(), ex=self.ttl_seconds
            )
        except RedisError:
            logger.warning("Cannot write batch details cache", exc_info=True)

    async def delete(self, batch_id: int) -> None:
        try:
            await self.client.delete(self._cache_key(batch_id))
        except RedisError:
            logger.warning("Cannot invalidate batch details cache", exc_info=True)
