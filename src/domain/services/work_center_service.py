from src.data.models import WorkCenter
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.work_center import (
    WorkCenterAlreadyExistsError,
    WorkCenterNotFoundError,
)


class WorkCenterService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

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
    ) -> WorkCenter:
        work_center = await self.uow.work_centers.get_by_id(work_center_id)
        if work_center is None:
            raise WorkCenterNotFoundError(work_center_id)

        return work_center

    async def delete(self, work_center_id: int) -> None:
        work_center = await self.get_by_id(work_center_id)

        await self.uow.work_centers.delete(work_center)
        await self.uow.commit()
