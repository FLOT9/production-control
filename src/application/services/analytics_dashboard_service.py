from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from src.application.dto.analytics import DashboardAnalytics
from src.core.config import settings
from src.data.unit_of_work import UnitOfWork
from src.storage.analytics_cache import AnalyticsCache


class AnalyticsDashboardService:
    def __init__(
        self, uow: UnitOfWork, cache: AnalyticsCache[DashboardAnalytics]
    ) -> None:
        self.uow = uow
        self.cache = cache

    async def get_dashboard(
        self,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        work_center_id: int | None = None,
        shift: str | None = None,
        force_refresh: bool = False,
        strict: bool = False,
        now: datetime | None = None,
    ) -> DashboardAnalytics:
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        now = now or datetime.now(UTC)
        today = now.astimezone(ZoneInfo(settings.production_timezone)).date()
        key = await self.cache.dashboard_key(
            today=today,
            date_from=date_from,
            date_to=date_to,
            work_center_id=work_center_id,
            shift=shift,
            strict=strict,
        )
        if not force_refresh:
            cached = await self.cache.get(key)
            if cached is not None:
                return cached
        snapshot = await self.uow.analytics.dashboard(
            today=today,
            date_from=date_from,
            date_to=date_to,
            work_center_id=work_center_id,
            shift=shift,
        )
        stored = snapshot.model_copy(update={"cached_at": datetime.now(UTC)})
        if await self.cache.set(key, stored, strict=strict):
            return stored
        return snapshot
