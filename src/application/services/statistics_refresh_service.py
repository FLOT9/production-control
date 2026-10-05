from datetime import date

from src.application.services.batch_service import BatchService
from src.application.services.dashboard_service import DashboardService
from src.data.unit_of_work import UnitOfWork


class StatisticsRefreshService:
    def __init__(
        self,
        uow: UnitOfWork,
        batch_service: BatchService,
        dashboard_service: DashboardService,
    ) -> None:
        self.uow = uow
        self.batch_service = batch_service
        self.dashboard_service = dashboard_service

    async def refresh_all(self, *, today: date, page_size: int = 200) -> dict[str, int]:
        if page_size <= 0:
            raise ValueError("page_size must be positive")
        after_id = 0
        updated = 0
        while True:
            ids = await self.uow.batches.list_ids(after_id=after_id, limit=page_size)
            if not ids:
                break
            updated += await self.batch_service.refresh_statistics(ids)
            # Release the read transaction between pages; no database writes occur here.
            await self.uow.rollback()
            after_id = ids[-1]
        await self.dashboard_service.refresh_summary()
        await self.dashboard_service.refresh_summary(batch_date=today)
        return {"batches_updated": updated, "dashboards_updated": 2}
