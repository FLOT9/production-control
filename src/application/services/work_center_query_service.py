from src.domain.services.work_center_service import WorkCenterService
from src.storage.work_center_cache import WorkCenterCache


class WorkCenterQueryService:
    def __init__(
        self,
        work_center_service: WorkCenterService,
        cache: WorkCenterCache,
    ) -> None:
        self.work_center_service = work_center_service
        self.cache = cache

    async def get_by_id(
        self,
        work_center_id: int,
    ) -> dict[str, object]:
        cached = await self.cache.get(work_center_id)

        if cached is not None:
            return cached

        work_center = await self.work_center_service.get_by_id(work_center_id)

        data: dict[str, object] = {
            "id": work_center.id,
            "identifier": work_center.identifier,
            "name": work_center.name,
            "created_at": work_center.created_at.isoformat(),
            "updated_at": work_center.updated_at.isoformat(),
        }

        await self.cache.set(work_center_id, data)
        return data
