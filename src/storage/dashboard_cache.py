import hashlib
import json
import logging
from datetime import date
from uuid import uuid4

from pydantic import TypeAdapter, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.application.dto.dashboard import DashboardSummary

logger = logging.getLogger(__name__)
summary_adapter = TypeAdapter(DashboardSummary)


class DashboardCache:
    def __init__(
        self, client: Redis, ttl_seconds: int, prefix: str = "dashboard-summary"
    ) -> None:
        self.client = client
        self.ttl_seconds = ttl_seconds
        self.prefix = prefix

    async def make_key(
        self,
        *,
        batch_date: date | None,
        work_center_id: int | None,
        shift: str | None,
        strict: bool = False,
    ) -> str | None:
        # Capture the generation BEFORE reading SQL. Late writes after
        # invalidation remain in the old generation and cannot refill the new one.
        try:
            version = await self.client.get(f"{self.prefix}:version")
            if version is None:
                await self.client.set(f"{self.prefix}:version", uuid4().hex, nx=True)
                version = await self.client.get(f"{self.prefix}:version")
            if version is None:
                if strict:
                    raise RedisError("Dashboard cache version is unavailable")
                return None
        except RedisError:
            logger.warning("Cannot read Dashboard cache version", exc_info=True)
            if strict:
                raise
            return None
        filters = json.dumps(
            [batch_date.isoformat() if batch_date else None, work_center_id, shift],
            ensure_ascii=False,
        )
        digest = hashlib.sha256(filters.encode()).hexdigest()
        return f"{self.prefix}:{version}:{digest}"

    async def get(self, key: str | None) -> DashboardSummary | None:
        if key is None:
            return None
        try:
            value = await self.client.get(key)
            return summary_adapter.validate_json(value) if value is not None else None
        except (RedisError, ValidationError):
            logger.warning("Cannot read Dashboard cache entry", exc_info=True)
            return None

    async def set(
        self, key: str | None, summary: DashboardSummary, *, strict: bool = False
    ) -> None:
        if key is None:
            if strict:
                raise RedisError("Dashboard cache key is unavailable")
            return
        value = summary_adapter.dump_json(summary)
        try:
            await self.client.set(key, value, ex=self.ttl_seconds)
        except RedisError:
            logger.warning("Cannot write Dashboard cache entry", exc_info=True)
            if strict:
                raise

    async def invalidate(self) -> None:
        try:
            await self.client.set(f"{self.prefix}:version", uuid4().hex)
        except RedisError:
            logger.warning("Cannot invalidate Dashboard cache", exc_info=True)
