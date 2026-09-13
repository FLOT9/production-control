from src.data.models import WorkCenter
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.work_center import (
    WorkCenterAlreadyExistsError,
    WorkCenterHasBatchesError,
    WorkCenterNotFoundError,
)
from src.storage.work_center_cache import WorkCenterCache


class WorkCenterService:
    def __init__(self, uow: UnitOfWork, cache: WorkCenterCache) -> None:
        self.uow = uow
        self.cache = cache

    async def create(
        self,
        identifier: str,
        name: str,
    ) -> WorkCenter:
        if await self.uow.work_centers.get_by_identifier(identifier):
            raise WorkCenterAlreadyExistsError(identifier)

        saved_work_center = await self.uow.work_centers.create(
            name=name, identifier=identifier
        )
        await self.uow.commit()

        return saved_work_center

    async def get_by_id(
        self,
        work_center_id: int,
    ) -> dict[str, object]:
        cached = await self.cache.get(work_center_id)

        if cached is not None:
            return cached

        work_center = await self._get_from_db(work_center_id)

        data: dict[str, object] = {
            "id": work_center.id,
            "identifier": work_center.identifier,
            "name": work_center.name,
            "created_at": work_center.created_at.isoformat(),
            "updated_at": work_center.updated_at.isoformat(),
        }

        await self.cache.set(work_center_id, data)
        return data

    async def _get_from_db(
        self,
        work_center_id: int,
    ) -> WorkCenter:
        work_center = await self.uow.work_centers.get_by_id(work_center_id)
        if work_center is None:
            raise WorkCenterNotFoundError(work_center_id)

        return work_center

    async def delete(self, work_center_id: int) -> None:
        work_center = await self._get_from_db(work_center_id)

        has_batches = await self.uow.batches.exists_by_work_center_id(work_center_id)
        if has_batches:
            raise WorkCenterHasBatchesError(work_center_id)

        await self.uow.work_centers.delete(work_center)
        await self.uow.commit()
        await self.cache.delete(work_center_id)
