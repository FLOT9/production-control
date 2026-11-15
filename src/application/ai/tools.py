from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import date

from langchain_core.tools import BaseTool, tool

from src.application.ai.schemas import BatchStatisticsArgs, FindBatchesArgs
from src.application.dto import BatchFilters
from src.application.dto.assistant import FoundBatch
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_service import BatchService


def create_statistics_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchAnalyticsService]],
) -> BaseTool:
    @tool(args_schema=BatchStatisticsArgs)
    async def get_batch_statistics(batch_id: int) -> dict[str, int]:
        """Получить количество изделий и остаток партии по-внутреннему ID."""
        async with service_factory() as service:
            statistics = await service.get_statistics(batch_id)
        return {
            "total": statistics.total_products,
            "aggregated": statistics.aggregated_products,
            "remaining": statistics.pending_products,
        }

    return get_batch_statistics


async def find_batches(
    service: BatchService,
    batch_number: int,
    batch_date: date | None = None,
    limit: int = 5,
) -> tuple[list[FoundBatch], int]:
    filters = BatchFilters(
        batch_number=batch_number,
        batch_date=batch_date,
    )

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
        batch_number: int,
        batch_date: date | None = None,
        limit: int = 5,
    ) -> dict[str, object]:
        """Найти партии по производственному номеру и необязательной дате.

        Номер партии отличается от внутреннего ID. Если найдено несколько
        партий, необходимо уточнить дату, а не выбирать первую.
        """
        async with service_factory() as service:
            items, total = await find_batches(
                service,
                batch_number=batch_number,
                batch_date=batch_date,
                limit=limit,
            )

        return {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
        }

    return search_batches
