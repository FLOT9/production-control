from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.dto import ProductionSummaryRow
from src.data.models import Batch, Product, WorkCenter


class ProductionSummaryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_rows(self) -> list[ProductionSummaryRow]:
        statement = (
            select(
                WorkCenter.identifier.label("work_center_identifier"),
                WorkCenter.name.label("work_center_name"),
                Batch.batch_number.label("batch_number"),
                Batch.batch_date.label("batch_date"),
                Batch.shift.label("shift"),
                Batch.team.label("team"),
                Batch.nomenclature.label("nomenclature"),
                Batch.ekn_code.label("ekn_code"),
                Batch.is_closed.label("is_closed"),
                func.count(Product.id).label("products_total"),
                func.count(Product.id)
                .filter(Product.is_aggregated.is_(True))
                .label("products_aggregated"),
            )
            .select_from(Batch)
            .join(
                WorkCenter,
                WorkCenter.id == Batch.work_center_id,
            )
            .outerjoin(
                Product,
                Product.batch_id == Batch.id,
            )
            .group_by(
                Batch.id,
                WorkCenter.identifier,
                WorkCenter.name,
                Batch.batch_number,
                Batch.batch_date,
                Batch.shift,
                Batch.team,
                Batch.nomenclature,
                Batch.ekn_code,
                Batch.is_closed,
            )
            .order_by(
                Batch.batch_date.desc(),
                Batch.batch_number.desc(),
            )
        )

        result = await self.session.execute(statement)

        return [ProductionSummaryRow(**dict(row)) for row in result.mappings().all()]
