from datetime import UTC, datetime

from src.application.analytics.calculator import batch_analytics
from src.application.dto.analytics import BatchAnalytics, BatchAnalyticsSnapshot
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchNotFoundError
from src.storage.analytics_cache import AnalyticsCache


class BatchAnalyticsService:
    def __init__(
        self, uow: UnitOfWork, cache: AnalyticsCache[BatchAnalyticsSnapshot]
    ) -> None:
        self.uow = uow
        self.cache = cache

    async def get_statistics(
        self, batch_id: int, *, now: datetime | None = None
    ) -> BatchAnalytics:
        now = now or datetime.now(UTC)
        key = await self.cache.batch_key(batch_id)
        snapshot = await self.cache.get(key)
        if snapshot is not None and snapshot.batch_info.id != batch_id:
            snapshot = None
        if snapshot is None:
            rows = await self.uow.analytics.batch_snapshots([batch_id], now=now)
            if not rows:
                raise BatchNotFoundError(batch_id)
            snapshot = rows[0]
            stored = snapshot.model_copy(update={"cached_at": datetime.now(UTC)})
            if await self.cache.set(key, stored):
                snapshot = stored
        return batch_analytics(snapshot, now)
