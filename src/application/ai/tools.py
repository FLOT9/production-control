from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from langchain_core.tools import BaseTool, tool

from src.application.ai.aggregation_day import resolve_aggregation_range
from src.application.ai.schemas import (
    AggregationDay,
    AggregationDayArgs,
    BatchStatisticsArgs,
    DashboardArgs,
    FindBatchesArgs,
)
from src.application.dto import BatchFilters
from src.application.dto.analytics import BatchComparisonRequest
from src.application.dto.assistant import FoundBatch
from src.application.services.analytics_dashboard_service import (
    AnalyticsDashboardService,
)
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_comparison_service import BatchComparisonService
from src.application.services.batch_service import BatchService
from src.core.config import settings


def create_statistics_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchAnalyticsService]],
) -> BaseTool:
    @tool(args_schema=BatchStatisticsArgs)
    async def get_batch_statistics(batch_id: int) -> dict[str, int | float | None]:
        """Получить количество изделий и остаток партии по-внутреннему ID."""
        async with service_factory() as service:
            statistics = await service.get_statistics(batch_id)
        return {
            "total": statistics.total_products,
            "aggregated": statistics.aggregated_products,
            "remaining": statistics.pending_products,
            "aggregation_percent": statistics.aggregation_percent,
            "products_per_hour": statistics.timeline.products_per_hour,
        }

    return get_batch_statistics


async def find_batches(
    service: BatchService,
    filters: BatchFilters,
    limit: int = 5,
) -> tuple[list[FoundBatch], int]:
    batches, total = await service.list_batches(filters=filters, limit=limit, offset=0)

    items: list[FoundBatch] = []
    for batch in batches:
        item = FoundBatch.model_validate(batch)
        items.append(item)

    return items, total


def create_find_batches_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchService]],
) -> BaseTool:
    @tool("find_batches", args_schema=FindBatchesArgs)
    async def search_batches(
        batch_number: int | None = None,
        batch_date: date | None = None,
        limit: int = 5,
        include_statistics: bool = False,
        date_from: date | None = None,
        date_to: date | None = None,
        work_center_id: int | None = None,
        shift: str | None = None,
        is_closed: bool | None = None,
        count_only: bool = False,
    ) -> dict[str, object]:
        """Найти или посчитать партии по номеру, датам, ID цеха, смене и статусу."""
        # include_statistics и count_only используются обработчиком ассистента.
        filters = BatchFilters(
            batch_number=batch_number,
            batch_date=batch_date,
            date_from=date_from,
            date_to=date_to,
            work_center_id=work_center_id,
            shift=shift,
            is_closed=is_closed,
        )
        async with service_factory() as service:
            items, total = await find_batches(service, filters, limit)

        return {
            "items": [
                item.model_dump(mode="json", exclude_none=True) for item in items
            ],
            "total": total,
        }

    return search_batches


def create_compare_batches_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchComparisonService]],
) -> BaseTool:
    @tool(args_schema=BatchComparisonRequest)
    async def compare_batches(batch_ids: list[int]) -> list[dict[str, int | float]]:
        """Сравнить изделия, остатки, выполнение и темп партий по внутренним ID."""
        async with service_factory() as service:
            comparison = await service.compare(batch_ids)

        return [
            {
                "batch_id": item.batch_info.id,
                "total_products": item.total_products,
                "aggregated_products": item.aggregated_products,
                "pending_products": item.pending_products,
                "aggregation_percent": item.aggregation_percent,
                "products_per_hour": item.products_per_hour,
            }
            for item in comparison.items
        ]

    return compare_batches


def create_dashboard_tool(
    service_factory: Callable[
        [], AbstractAsyncContextManager[AnalyticsDashboardService]
    ],
) -> BaseTool:
    @tool(args_schema=DashboardArgs)
    async def get_dashboard(
        date_from: date,
        date_to: date,
        work_center_id: int | None = None,
        shift: str | None = None,
    ) -> dict[str, int]:
        """Получить число агрегированных изделий в партиях за выбранные даты."""
        async with service_factory() as service:
            result = await service.get_dashboard(
                date_from=date_from,
                date_to=date_to,
                work_center_id=work_center_id,
                shift=shift,
            )
        return {"aggregated_products": result.summary.aggregated_products}

    return get_dashboard


def create_aggregation_day_tool(
    service_factory: Callable[
        [], AbstractAsyncContextManager[AnalyticsDashboardService]
    ],
) -> BaseTool:
    @tool(args_schema=AggregationDayArgs)
    async def count_aggregated_on(
        day: AggregationDay | None = None,
        work_center_id: int | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
        period: Literal["last_week"] | None = None,
    ) -> dict[str, int]:
        """Посчитать изделия по дате операции за день или период, опционально по ID цеха."""
        request = AggregationDayArgs(
            day=day,
            date_from=date_from,
            date_to=date_to,
            period=period,
            work_center_id=work_center_id,
        )
        start, end = resolve_aggregation_range(
            request, datetime.now(UTC), ZoneInfo(settings.production_timezone)
        )
        async with service_factory() as service:
            if work_center_id is not None:
                if start == end:
                    (
                        confirmed,
                        unknown,
                    ) = await service.count_aggregated_on_by_work_center(
                        start, work_center_id=work_center_id
                    )
                else:
                    (
                        confirmed,
                        unknown,
                    ) = await service.count_aggregated_between_by_work_center(
                        start, end, work_center_id=work_center_id
                    )
                return {
                    "aggregated_products": confirmed,
                    "unknown_work_center_count": unknown,
                }
            if start == end:
                count = await service.count_aggregated_on(start)
            else:
                count = await service.count_aggregated_between(start, end)
        return {"aggregated_products": count}

    return count_aggregated_on
