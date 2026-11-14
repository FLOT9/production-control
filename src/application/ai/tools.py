from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, ConfigDict, Field

from src.application.services.batch_analytics_service import BatchAnalyticsService


class BatchStatisticsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: int = Field(gt=0, le=2**31 - 1)


def create_statistics_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchAnalyticsService]],
) -> BaseTool:
    @tool(args_schema=BatchStatisticsArgs)
    async def get_batch_statistics(batch_id: int) -> dict[str, int]:
        """Получить количество изделий и остаток партии по внутреннему ID."""
        async with service_factory() as service:
            statistics = await service.get_statistics(batch_id)
        return {
            "total": statistics.total_products,
            "aggregated": statistics.aggregated_products,
            "remaining": statistics.pending_products,
        }

    return get_batch_statistics
