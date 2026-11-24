from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.application.dto.analytics import DashboardAnalytics
from src.core.config import settings
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.work_center import WorkCenterNotFoundError
from src.storage.analytics_cache import AnalyticsCache


class AnalyticsDashboardService:
    def __init__(
        self, uow: UnitOfWork, cache: AnalyticsCache[DashboardAnalytics]
    ) -> None:
        self.uow = uow
        self.cache = cache

    @staticmethod
    def _aggregation_bounds(
        date_from: date, date_to: date
    ) -> tuple[datetime, datetime]:
        if date_from > date_to:
            raise ValueError("date_from must not be after date_to")
        timezone = ZoneInfo(settings.production_timezone)
        start_local = datetime.combine(date_from, time.min, tzinfo=timezone)
        end_local = datetime.combine(
            date_to + timedelta(days=1), time.min, tzinfo=timezone
        )
        return start_local.astimezone(UTC), end_local.astimezone(UTC)

    async def count_aggregated_on(self, day: date) -> int:
        return await self.count_aggregated_between(day, day)

    async def count_aggregated_between(self, date_from: date, date_to: date) -> int:
        start_utc, end_utc = self._aggregation_bounds(date_from, date_to)
        return await self.uow.analytics.count_aggregated_products(start_utc, end_utc)

    async def count_aggregated_on_by_work_center(
        self, day: date, *, work_center_id: int
    ) -> tuple[int, int]:
        return await self.count_aggregated_between_by_work_center(
            day, day, work_center_id=work_center_id
        )

    async def count_aggregated_between_by_work_center(
        self, date_from: date, date_to: date, *, work_center_id: int
    ) -> tuple[int, int]:
        if await self.uow.work_centers.get_by_id(work_center_id) is None:
            raise WorkCenterNotFoundError(work_center_id)
        start_utc, end_utc = self._aggregation_bounds(date_from, date_to)
        return await self.uow.analytics.count_aggregated_products_by_work_center(
            start_utc, end_utc, work_center_id=work_center_id
        )

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
