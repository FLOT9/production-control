import asyncio

from langchain_core.tools import tool

from scripts.llm_dependencies import batch_analytics_service
from src.application.ai.assistant_service import AssistantService
from src.core.config import settings
from src.integrations.llm.factory import create_gigachat


async def main() -> None:
    assistant = AssistantService(create_gigachat(settings), get_batch_statistics)
    answer = await assistant.ask("Сколько изделий осталось в партии с ID 1?")
    print(answer)


@tool
async def get_batch_statistics(batch_id: int) -> dict[str, int]:
    """Получить количество изделий и остаток производственной партии"""

    async with batch_analytics_service() as service:
        statistics = await service.get_statistics(batch_id)

    return {
        "total": statistics.total_products,
        "aggregated": statistics.aggregated_products,
        "remaining": statistics.pending_products,
    }


if __name__ == "__main__":
    asyncio.run(main())
