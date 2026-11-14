import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import APIKeyHeader

from src.application.ai.assistant_service import AssistantService
from src.application.ai.exceptions import AssistantNotConfiguredError
from src.application.ai.tools import create_statistics_tool
from src.core.assistant_dependencies import batch_analytics_service
from src.core.config import settings
from src.integrations.llm.adapter import LangChainModelAdapter
from src.integrations.llm.factory import gigachat_model

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_assistant_key(
    api_key: Annotated[str | None, Security(api_key_header)],
) -> None:
    expected = settings.assistant_api_key
    if expected is None or not expected.get_secret_value():
        raise AssistantNotConfiguredError()
    if api_key is None or not secrets.compare_digest(
        api_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(401, "Неверный ключ")


async def get_assistant_service(
    _authorized: Annotated[None, Depends(verify_assistant_key)],
) -> AsyncIterator[AssistantService]:
    async with gigachat_model(settings) as model:
        tool = create_statistics_tool(batch_analytics_service)
        yield AssistantService(
            LangChainModelAdapter(model, tool),
            tool,
            timeout_seconds=settings.assistant_timeout_seconds,
        )


AssistantServiceDep = Annotated[AssistantService, Depends(get_assistant_service)]
