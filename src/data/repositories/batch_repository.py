from datetime import date

from sqlalchemy import ColumnElement, exists, func, select
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

    def _build_filter_conditions(
        self,
        *,
        is_closed: bool | None,
        batch_number: int | None,
        batch_date: date | None,
        work_center_id: int | None,
        shift: str | None,
    ) -> list[ColumnElement[bool]]:
        conditions = []

        if is_closed is not None:
            conditions.append(Batch.is_closed == is_closed)

        if batch_number is not None:
            conditions.append(Batch.batch_number == batch_number)

        if batch_date is not None:
            conditions.append(Batch.batch_date == batch_date)

        if work_center_id is not None:
            conditions.append(Batch.work_center_id == work_center_id)

        if shift is not None:
            conditions.append(Batch.shift == shift)

        return conditions

    async def find_by_filters(
        self,
        *,
        is_closed: bool | None,
        offset: int,
        limit: int,
        batch_number: int | None,
        batch_date: date | None,
        work_center_id: int | None,
        shift: str | None,
    ) -> list[Batch]:
        conditions = self._build_filter_conditions(
            is_closed=is_closed,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )

        statement = (
            select(Batch)
            .where(*conditions)
            .order_by(
                Batch.batch_date.desc(),
                Batch.id.desc(),
            )
            .offset(offset)
            .limit(limit)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def count_by_filters(
        self,
        *,
        is_closed: bool | None,
        batch_number: int | None,
        batch_date: date | None,
        work_center_id: int | None,
        shift: str | None,
    ) -> int:
        conditions = self._build_filter_conditions(
            is_closed=is_closed,
            batch_number=batch_number,
            batch_date=batch_date,
            work_center_id=work_center_id,
            shift=shift,
        )

        statement = select(func.count(Batch.id)).where(*conditions)

        total = await self.session.scalar(statement)

        return int(total or 0)
