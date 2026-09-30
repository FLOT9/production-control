from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
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

    async def get_or_create_by_identifier(
        self,
        identifier: str,
        name: str,
    ) -> WorkCenter:
        statement = (
            insert(WorkCenter)
            .values(identifier=identifier, name=name)
            .on_conflict_do_nothing(index_elements=[WorkCenter.identifier])
            .returning(WorkCenter)
        )
        created = await self.session.scalar(statement)
        if created is not None:
            return created

        # A concurrent insert can win; read its committed row in a new statement.
        existing = await self.get_by_identifier(identifier)
        if existing is None:
            raise RuntimeError("Work center disappeared after an insert conflict")
        return existing
