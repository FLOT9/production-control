import asyncio

from src.application.ai.assistant_service import AssistantService
from src.application.ai.tools import create_find_batches_tool, create_statistics_tool
from src.core.assistant_dependencies import (
    batch_analytics_service,
    batch_search_service,
)
from src.core.config import settings
from src.core.database import dispose_engine
from src.integrations.llm.adapter import LangChainModelAdapter
from src.integrations.llm.factory import gigachat_model


async def main() -> None:
    try:
        async with gigachat_model(settings) as model:
            tools = [
                create_statistics_tool(batch_analytics_service),
                create_find_batches_tool(batch_search_service),
            ]
            assistant = AssistantService(
                LangChainModelAdapter(model, tools),
                tools,
                timeout_seconds=settings.assistant_timeout_seconds,
            )
            result = await assistant.ask("Сколько изделий осталось в партии с ID 1?")
            print(result.answer)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
