from datetime import date, datetime

from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.application.dto import BatchFilters, BatchProductCounts
from src.data.models import Batch, Product
from src.data.repositories.base_repository import BaseRepository


class BatchRepository(BaseRepository[Batch]):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, Batch)

    async def get_by_id_for_update(self, batch_id: int) -> Batch | None:
        statement = select(Batch).where(Batch.id == batch_id).with_for_update()
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def get_with_products(self, batch_id: int) -> Batch | None:
        statement = (
            select(Batch)
            .where(Batch.id == batch_id)
            .options(selectinload(Batch.products))
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_ids(self, *, after_id: int, limit: int) -> list[int]:
        statement = (
            select(Batch.id).where(Batch.id > after_id).order_by(Batch.id).limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_expired_ids(
        self,
        *,
        expired_before: datetime,
        after_id: int,
        limit: int,
    ) -> list[int]:
        statement = (
            select(Batch.id)
            .where(
                Batch.is_closed.is_(False),
                Batch.shift_end < expired_before,
                Batch.id > after_id,
            )
            .order_by(Batch.id)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

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

    async def get_statistics(
        self,
        batch_id: int,
    ) -> BatchProductCounts | None:
        rows = await self.get_statistics_many([batch_id])
        return rows[0] if rows else None

    async def get_statistics_many(
        self,
        batch_ids: list[int],
    ) -> list[BatchProductCounts]:
        statement = (
            select(
                Batch.id.label("batch_id"),
                func.count(Product.id).label("total_products"),
                func.count(Product.id)
                .filter(Product.is_aggregated.is_(True))
                .label("aggregated_products"),
            )
            .outerjoin(Product, Product.batch_id == Batch.id)
            .where(Batch.id.in_(batch_ids))
            .group_by(Batch.id)
        )
        result = await self.session.execute(statement)
        return [
            BatchProductCounts(
                batch_id=row.batch_id,
                total_products=row.total_products,
                aggregated_products=row.aggregated_products,
            )
            for row in result.all()
        ]

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
        filters: BatchFilters,
    ) -> list[ColumnElement[bool]]:
        conditions = []

        if filters.is_closed is not None:
            conditions.append(Batch.is_closed == filters.is_closed)

        if filters.batch_number is not None:
            conditions.append(Batch.batch_number == filters.batch_number)

        if filters.batch_date is not None:
            conditions.append(Batch.batch_date == filters.batch_date)

        if filters.work_center_id is not None:
            conditions.append(Batch.work_center_id == filters.work_center_id)

        if filters.shift is not None:
            conditions.append(Batch.shift == filters.shift)

        return conditions

    async def find_by_filters(
        self,
        *,
        filters: BatchFilters,
        offset: int,
        limit: int,
    ) -> list[Batch]:
        conditions = self._build_filter_conditions(filters=filters)

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
        filters: BatchFilters,
    ) -> int:
        conditions = self._build_filter_conditions(filters=filters)

        statement = select(func.count(Batch.id)).where(*conditions)

        total = await self.session.scalar(statement)

        return int(total or 0)

    async def list_for_export(
        self,
        *,
        filters: BatchFilters,
    ) -> list[Batch]:
        conditions = self._build_filter_conditions(filters=filters)
        statement = (
            select(Batch)
            .where(*conditions)
            .order_by(Batch.batch_date.desc(), Batch.id.desc())
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())
