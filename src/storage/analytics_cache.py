import hashlib
import json
import logging
from datetime import date
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from src.storage.batch_statistics_cache import BatchStatisticsCache
from src.storage.dashboard_cache import DashboardCache

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)


class AnalyticsCache(Generic[T]):
    def __init__(self, client: Redis, model: type[T], ttl_seconds: int) -> None:
        self.client = client
        self.model = model
        self.ttl_seconds = ttl_seconds

    async def dashboard_key(
        self,
        *,
        today: date,
        date_from: date | None,
        date_to: date | None,
        work_center_id: int | None,
        shift: str | None,
        strict: bool = False,
    ) -> str | None:
        # Share the existing generation so all existing mutation paths invalidate analytics.
        base = await DashboardCache(self.client, self.ttl_seconds).make_key(
            batch_date=None, work_center_id=work_center_id, shift=shift, strict=strict
        )
        if base is None:
            return None
        digest = hashlib.sha256(
            json.dumps(
                [
                    today.isoformat(),
                    date_from.isoformat() if date_from else None,
                    date_to.isoformat() if date_to else None,
                ]
            ).encode()
        ).hexdigest()
        return f"{base}:analytics:v1:{digest}"

    async def batch_key(self, batch_id: int) -> str | None:
        base = await BatchStatisticsCache(self.client, self.ttl_seconds).make_key(
            batch_id
        )
        return f"{base}:analytics:v1" if base is not None else None

    async def get(self, key: str | None) -> T | None:
        if key is None:
            return None
        try:
            value = await self.client.get(key)
            return self.model.model_validate_json(value) if value is not None else None
        except (RedisError, ValidationError):
            logger.warning("Cannot read analytics cache", exc_info=True)
            return None

    async def set(self, key: str | None, value: T, *, strict: bool = False) -> bool:
        if key is None:
            if strict:
                raise RedisError("Analytics cache key is unavailable")
            return False
        try:
            await self.client.set(key, value.model_dump_json(), ex=self.ttl_seconds)
            return True
        except RedisError:
            logger.warning("Cannot write analytics cache", exc_info=True)
            if strict:
                raise
            return False
