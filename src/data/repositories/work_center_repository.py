from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import WorkCenter
from src.data.repositories.base_repository import BaseRepository


class WorkCenterRepository(BaseRepository[WorkCenter]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WorkCenter)

    async def get_by_identifier(
        self,
        identifier: str,
    ) -> WorkCenter | None:
        statement = select(WorkCenter).where(WorkCenter.identifier == identifier)
        result = await self.session.execute(statement)

        return result.scalar_one_or_none()
