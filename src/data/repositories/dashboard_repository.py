from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dto.dashboard import DashboardCounts
from src.data.models import Batch, Product


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_summary(
        self,
        *,
        batch_date: date | None,
        work_center_id: int | None,
        shift: str | None,
    ) -> DashboardCounts:

        conditions = []

        if batch_date is not None:
            conditions.append(Batch.batch_date == batch_date)

        if work_center_id is not None:
            conditions.append(Batch.work_center_id == work_center_id)

        if shift is not None:
            conditions.append(Batch.shift == shift)

        statement = (
            select(
                func.count(func.distinct(Batch.id)).label("total_batches"),
                func.count(func.distinct(Batch.id))
                .filter(Batch.is_closed.is_(True))
                .label("closed_batches"),
                func.count(Product.id).label("total_products"),
                func.count(Product.id)
                .filter(Product.is_aggregated.is_(True))
                .label("aggregated_products"),
            )
            .select_from(Batch)
            .outerjoin(
                Product,
                Product.batch_id == Batch.id,
            )
            .where(*conditions)
        )

        result = await self.session.execute(statement)
        row = result.one()

        return DashboardCounts(
            total_batches=row.total_batches,
            closed_batches=row.closed_batches,
            total_products=row.total_products,
            aggregated_products=row.aggregated_products,
        )
