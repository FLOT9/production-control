from datetime import UTC, date, datetime
from typing import overload

from sqlalchemy import (
    Integer,
    String,
    case,
    cast,
    func,
    literal,
    null,
    select,
    union_all,
)
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.analytics.calculator import dashboard_metrics
from src.application.dto.analytics import (
    BatchAnalyticsSnapshot,
    BatchInfo,
    DashboardAnalytics,
    ShiftMetrics,
    WorkCenterMetrics,
)
from src.data.models import Batch, Product, WorkCenter


@overload
def utc(value: datetime) -> datetime: ...


@overload
def utc(value: None) -> None: ...


def utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def dashboard(
        self,
        *,
        today: date,
        date_from: date | None,
        date_to: date | None,
        work_center_id: int | None,
        shift: str | None,
    ) -> DashboardAnalytics:
        conditions = []
        if date_from is not None:
            conditions.append(Batch.batch_date >= date_from)
        if date_to is not None:
            conditions.append(Batch.batch_date <= date_to)
        if work_center_id is not None:
            conditions.append(Batch.work_center_id == work_center_id)
        if shift is not None:
            conditions.append(Batch.shift == shift)
        # One row per batch first; the following rollups never multiply batch counts.
        base = (
            select(
                Batch.id,
                Batch.batch_date,
                Batch.shift,
                Batch.work_center_id,
                WorkCenter.name,
                case((Batch.is_closed.is_(True), 1), else_=0).label("closed"),
                func.count(Product.id).label("total"),
                func.count(Product.id)
                .filter(Product.is_aggregated.is_(True))
                .label("aggregated"),
            )
            .join(WorkCenter, WorkCenter.id == Batch.work_center_id)
            .outerjoin(Product, Product.batch_id == Batch.id)
            .where(*conditions)
            .group_by(
                Batch.id,
                Batch.batch_date,
                Batch.shift,
                Batch.work_center_id,
                WorkCenter.name,
                Batch.is_closed,
            )
            .cte("batch_counts")
        )
        columns = [
            func.count(base.c.id).label("total_batches"),
            func.coalesce(func.sum(base.c.closed), 0).label("closed_batches"),
            func.coalesce(func.sum(base.c.total), 0).label("total_products"),
            func.coalesce(func.sum(base.c.aggregated), 0).label("aggregated_products"),
        ]
        summary = select(
            literal("summary").label("kind"),
            cast(null(), String).label("name"),
            cast(null(), Integer).label("work_center_id"),
            *columns,
        ).select_from(base)
        today_query = (
            select(
                literal("today"), cast(null(), String), cast(null(), Integer), *columns
            )
            .select_from(base)
            .where(base.c.batch_date == today)
        )
        shifts = (
            select(literal("shift"), base.c.shift, cast(null(), Integer), *columns)
            .select_from(base)
            .group_by(base.c.shift)
        )
        centers = (
            select(
                literal("center").label("kind"),
                base.c.name.label("name"),
                base.c.work_center_id.label("work_center_id"),
                *columns,
            )
            .select_from(base)
            .group_by(base.c.work_center_id, base.c.name)
            .order_by(func.sum(base.c.aggregated).desc(), base.c.work_center_id)
            .limit(5)
            .subquery()
        )
        # A single SQL statement supplies a consistent snapshot for all dashboard blocks.
        result = await self.session.execute(
            union_all(summary, today_query, shifts, select(centers))
        )
        by_shift = []
        top = []
        metrics_by_kind = {}
        for row in result.mappings():
            metrics = dashboard_metrics(
                int(row["total_batches"]),
                int(row["closed_batches"]),
                int(row["total_products"]),
                int(row["aggregated_products"]),
            )
            if row["kind"] == "shift":
                by_shift.append(ShiftMetrics(**metrics.model_dump(), shift=row["name"]))
            elif row["kind"] == "center":
                top.append(
                    WorkCenterMetrics(
                        **metrics.model_dump(),
                        work_center_id=row["work_center_id"],
                        name=row["name"],
                    )
                )
            else:
                metrics_by_kind[row["kind"]] = metrics
        return DashboardAnalytics(
            summary=metrics_by_kind["summary"],
            today=metrics_by_kind["today"],
            by_shift=sorted(by_shift, key=lambda item: item.shift),
            top_work_centers=sorted(
                top, key=lambda item: (-item.aggregated_products, item.work_center_id)
            ),
        )

    async def batch_snapshots(
        self, batch_ids: list[int], *, now: datetime
    ) -> list[BatchAnalyticsSnapshot]:
        if not batch_ids:
            return []
        window_end = case(
            (
                Batch.is_closed.is_(True)
                & Batch.closed_at.is_not(None)
                & (Batch.closed_at < Batch.shift_end),
                Batch.closed_at,
            ),
            else_=Batch.shift_end,
        )
        valid_window = (
            Product.is_aggregated.is_(True)
            & (Product.aggregated_at >= Batch.shift_start)
            & (Product.aggregated_at <= window_end)
            & (Product.aggregated_at <= now)
        )
        products = (
            select(
                Product.batch_id,
                func.count(Product.id).label("total_products"),
                func.count(Product.id)
                .filter(Product.is_aggregated.is_(True))
                .label("aggregated_products"),
                func.count(Product.id).filter(valid_window).label("window_products"),
                func.max(Product.aggregated_at)
                .filter(Product.is_aggregated.is_(True))
                .label("last_aggregated_at"),
            )
            .join(Batch, Product.batch_id == Batch.id)
            .where(Product.batch_id.in_(batch_ids))
            .group_by(Product.batch_id)
            .subquery()
        )
        statement = (
            select(
                Batch,
                WorkCenter.name.label("work_center_name"),
                func.coalesce(products.c.total_products, 0).label("total_products"),
                func.coalesce(products.c.aggregated_products, 0).label(
                    "aggregated_products"
                ),
                func.coalesce(products.c.window_products, 0).label("window_products"),
                products.c.last_aggregated_at,
            )
            .join(WorkCenter, WorkCenter.id == Batch.work_center_id)
            .outerjoin(products, products.c.batch_id == Batch.id)
            .where(Batch.id.in_(batch_ids))
            .execution_options(populate_existing=True)
        )
        result = await self.session.execute(statement)
        snapshots = []
        for row in result:
            batch = row.Batch
            info = BatchInfo(
                id=batch.id,
                batch_number=batch.batch_number,
                batch_date=batch.batch_date,
                nomenclature=batch.nomenclature,
                work_center_id=batch.work_center_id,
                work_center_name=row.work_center_name,
                shift=batch.shift,
                team=batch.team,
                is_closed=batch.is_closed,
                shift_start=utc(batch.shift_start),
                shift_end=utc(batch.shift_end),
                closed_at=utc(batch.closed_at),
            )
            snapshots.append(
                BatchAnalyticsSnapshot(
                    batch_info=info,
                    total_products=row.total_products,
                    aggregated_products=row.aggregated_products,
                    window_products=row.window_products,
                    last_aggregated_at=utc(row.last_aggregated_at),
                    observed_at=now,
                )
            )
        return snapshots
