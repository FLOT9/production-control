import hashlib
import json
import logging
from datetime import date
from uuid import uuid4

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.application.dto import BatchFilters
from src.data.models import Batch

logger = logging.getLogger(__name__)


class _BatchEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_description: str
    work_center_id: int
    shift: str
    team: str
    batch_number: int
    batch_date: date
    nomenclature: str
    ekn_code: str
    shift_start: AwareDatetime
    shift_end: AwareDatetime
    is_closed: bool
    closed_at: AwareDatetime | None
    created_at: AwareDatetime
    updated_at: AwareDatetime


class _BatchListEntry(BaseModel):
    items: list[_BatchEntry]
    total: int = Field(ge=0)


class BatchListCache:
    def __init__(
        self, client: Redis, ttl_seconds: int, prefix: str = "batch-list"
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    async def make_key(
        self,
        *,
        filters: BatchFilters,
        offset: int,
        limit: int,
    ) -> str | None:
        # Capture the version before SQL so late writes cannot refill a newer version.
        try:
            version = await self.client.get(f"{self.prefix}:version")
            if version is None:
                await self.client.set(f"{self.prefix}:version", uuid4().hex, nx=True)
                version = await self.client.get(f"{self.prefix}:version")
            if version is None:
                return None
        except RedisError:
            logger.warning("Cannot read batch list cache version", exc_info=True)
            return None
        key_data = json.dumps(
            [
                filters.is_closed,
                offset,
                limit,
                filters.batch_number,
                filters.batch_date.isoformat() if filters.batch_date else None,
                filters.work_center_id,
                filters.shift,
            ],
            ensure_ascii=False,
        )
        digest = hashlib.sha256(key_data.encode()).hexdigest()
        return f"{self.prefix}:{version}:{digest}"

    async def get(self, key: str | None) -> tuple[list[dict[str, object]], int] | None:
        if key is None:
            return None
        try:
            value = await self.client.get(key)
            if value is None:
                return None
            entry = _BatchListEntry.model_validate_json(value)
        except (RedisError, ValidationError):
            logger.warning("Cannot read batch list cache entry", exc_info=True)
            return None
        return [item.model_dump() for item in entry.items], entry.total

    async def set(self, key: str | None, batches: list[Batch], total: int) -> None:
        if key is None:
            return
        entry = _BatchListEntry(
            items=[_BatchEntry.model_validate(batch) for batch in batches], total=total
        )
        try:
            await self.client.set(key, entry.model_dump_json(), ex=self.ttl_seconds)
        except RedisError:
            logger.warning("Cannot write batch list cache entry", exc_info=True)

    async def invalidate(self) -> None:
        try:
            await self.client.set(f"{self.prefix}:version", uuid4().hex)
        except RedisError:
            logger.warning("Cannot invalidate batch list cache", exc_info=True)
