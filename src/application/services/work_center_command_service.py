from src.domain.services.work_center_service import WorkCenterService
from src.storage.work_center_cache import WorkCenterCache


class WorkCenterCommandService:
    def __init__(
        self,
        work_center_service: WorkCenterService,
        cache: WorkCenterCache,
    ) -> None:
        self.work_center_service = work_center_service
        self.cache = cache

    async def delete(self, work_center_id: int) -> None:
        await self.work_center_service.delete(work_center_id)
        await self.cache.delete(work_center_id)
