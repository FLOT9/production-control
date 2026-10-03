import logging
from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.data.models import Batch
from src.storage.batch_list_cache import _BatchEntry
from src.storage.cache_generation import read_generation

logger = logging.getLogger(__name__)


class _ProductEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    unique_code: str
    is_aggregated: bool
    aggregated_at: datetime | None


class _BatchDetailsEntry(_BatchEntry):
    products: list[_ProductEntry]


class BatchDetailsCache:
    def __init__(
        self, client: Redis, ttl_seconds: int, prefix: str = "batch-details"
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    def _generation_key(self, batch_id: int) -> str:
        return f"{self.prefix}:v3:{batch_id}:generation"

    async def make_key(self, batch_id: int, *, create: bool = True) -> str | None:
        generation_key = self._generation_key(batch_id)

        try:
            generation = await read_generation(
                self.client, generation_key, self.ttl_seconds, create=create
            )

            if generation is None:
                return None

            return f"{self.prefix}:v3:{batch_id}:data:{generation}"

        except RedisError:
            logger.warning(
                "Cannot read batch details cache generation for batch %s",
                batch_id,
                exc_info=True,
            )
            return None

    async def get(self, key: str | None, batch_id: int) -> dict[str, object] | None:
        if key is None:
            return None
        try:
            value = await self.client.get(key)
            if value is None:
                return None

            entry = _BatchDetailsEntry.model_validate_json(value)
            if entry.id != batch_id:
                logger.warning("Cached batch ID mismatch for %s", batch_id)
                return None

            return entry.model_dump()
        except (RedisError, ValidationError):
            logger.warning("Cannot read batch details cache", exc_info=True)
            return None

    async def set(self, key: str | None, batch: Batch) -> None:
        if key is None:
            return

        entry = _BatchDetailsEntry.model_validate(batch)
        try:
            await self.client.set(key, entry.model_dump_json(), ex=self.ttl_seconds)
        except RedisError:
            logger.warning("Cannot write batch details cache", exc_info=True)

    async def invalidate(self, batch_id: int) -> None:
        try:
            await self.client.set(
                self._generation_key(batch_id), uuid4().hex, ex=self.ttl_seconds * 2
            )
        except RedisError:
            logger.warning("Cannot invalidate batch details cache", exc_info=True)
