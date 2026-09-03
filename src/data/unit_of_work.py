from sqlalchemy.ext.asyncio import AsyncSession

from src.data.repositories.batch_repository import BatchRepository
from src.data.repositories.work_center_repository import (
    WorkCenterRepository,
)


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.work_centers = WorkCenterRepository(session)
        self.batches = BatchRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
