from datetime import date

from src.application.dto.dashboard import DashboardSummary
from src.data.unit_of_work import UnitOfWork
from src.storage.dashboard_cache import DashboardCache


class DashboardService:
    def __init__(self, uow: UnitOfWork, cache: DashboardCache) -> None:
        self.uow = uow
        self.cache = cache

    async def get_summary(
        self,
        *,
        batch_date: date | None = None,
        work_center_id: int | None = None,
        shift: str | None = None,
    ) -> DashboardSummary:
        key = await self.cache.make_key(
            batch_date=batch_date, work_center_id=work_center_id, shift=shift
        )
        cached = await self.cache.get(key)
        if cached is not None:
            return cached
        summary = await self._read_summary(
            batch_date=batch_date, work_center_id=work_center_id, shift=shift
        )
        await self.cache.set(key, summary)
        return summary

    async def refresh_summary(
        self, *, batch_date: date | None = None
    ) -> DashboardSummary:
        key = await self.cache.make_key(
            batch_date=batch_date, work_center_id=None, shift=None, strict=True
        )
        summary = await self._read_summary(
            batch_date=batch_date, work_center_id=None, shift=None
        )
        await self.cache.set(key, summary, strict=True)
        return summary

    async def _read_summary(
        self, *, batch_date: date | None, work_center_id: int | None, shift: str | None
    ) -> DashboardSummary:
        counts = await self.uow.dashboard.get_summary(
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )
        percent = (
            counts.aggregated_products / counts.total_products * 100
            if counts.total_products
            else 0.0
        )
        return DashboardSummary(
            total_batches=counts.total_batches,
            open_batches=counts.total_batches - counts.closed_batches,
            closed_batches=counts.closed_batches,
            total_products=counts.total_products,
            aggregated_products=counts.aggregated_products,
            pending_products=counts.total_products - counts.aggregated_products,
            aggregation_percent=round(percent, 2),
        )
