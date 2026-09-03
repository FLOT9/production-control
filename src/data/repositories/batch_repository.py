from datetime import date

from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import Batch
from src.data.repositories.base_repository import BaseRepository


class BatchRepository(BaseRepository[Batch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Batch)

    async def get_by_number_and_date(
        self,
        batch_number: int,
        batch_date: date,
    ) -> Batch | None:
        statement = select(Batch).where(
            Batch.batch_number == batch_number,
            Batch.batch_date == batch_date,
        )
        result = await self.session.execute(statement)

        return result.scalar_one_or_none()

    async def exists_by_work_center_id(
        self,
        work_center_id: int,
    ) -> bool:
        statement = select(exists().where(Batch.work_center_id == work_center_id))
        result = bool(await self.session.scalar(statement))

        return result
