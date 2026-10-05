from datetime import UTC, datetime

from src.application.dto.batch_report import (
    BatchReportData,
    BatchReportInfo,
    BatchReportProduct,
)
from src.application.dto.batch_statistics import BatchStatistics
from src.data.unit_of_work import UnitOfWork
from src.domain.exceptions.batch import BatchNotFoundError


class BatchReportService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def collect(self, batch_id: int) -> BatchReportData:
        batch = await self.uow.batches.get_with_products(batch_id)
        if batch is None:
            raise BatchNotFoundError(batch_id)

        products = tuple(
            BatchReportProduct(
                id=product.id,
                unique_code=product.unique_code,
                is_aggregated=product.is_aggregated,
                aggregated_at=product.aggregated_at,
                created_at=product.created_at,
            )
            for product in sorted(batch.products, key=lambda product: product.id)
        )
        total = len(products)
        aggregated = 0
        for product in products:
            if product.is_aggregated:
                aggregated += 1

        statistics = BatchStatistics(
            batch_id=batch.id,
            total_products=total,
            aggregated_products=aggregated,
            pending_products=total - aggregated,
            aggregation_percent=aggregated / total * 100 if total > 0 else 0.0,
        )
        return BatchReportData(
            batch=BatchReportInfo(
                id=batch.id,
                task_description=batch.task_description,
                work_center_id=batch.work_center_id,
                shift=batch.shift,
                team=batch.team,
                batch_number=batch.batch_number,
                batch_date=batch.batch_date,
                nomenclature=batch.nomenclature,
                ekn_code=batch.ekn_code,
                shift_start=batch.shift_start,
                shift_end=batch.shift_end,
                is_closed=batch.is_closed,
                closed_at=batch.closed_at,
                created_at=batch.created_at,
                updated_at=batch.updated_at,
            ),
            products=products,
            statistics=statistics,
            generated_at=datetime.now(UTC),
        )
