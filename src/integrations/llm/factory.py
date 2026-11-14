import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from gigachat.exceptions import GigaChatException
from langchain_gigachat import GigaChat
from pydantic import ValidationError

from src.application.ai.exceptions import (
    AssistantNotConfiguredError,
    LLMUnavailableError,
)
from src.core.config import Settings

logger = logging.getLogger(__name__)


def create_gigachat(settings: Settings) -> GigaChat:
    """Create a model from application settings without sending a request."""
    if (
        settings.gigachat_auth_key is None
        or not settings.gigachat_auth_key.get_secret_value()
    ):
        raise AssistantNotConfiguredError()

    return GigaChat(
        credentials=settings.gigachat_auth_key.get_secret_value(),
        scope="GIGACHAT_API_PERS",
        model=settings.gigachat_model,
        timeout=settings.gigachat_timeout_seconds,
        base_url="https://api.giga.chat/v1",
        max_tokens=100,
        max_retries=0,
        verify_ssl_certs=True,
        ca_bundle_file=settings.gigachat_ca_bundle_file,
    )


@asynccontextmanager
async def gigachat_model(settings: Settings) -> AsyncIterator[GigaChat]:
    """Own the provider client lifecycle inside the integration boundary."""
    try:
        model = create_gigachat(settings)
        client = model._client
    except (ValidationError, OSError) as error:
        raise AssistantNotConfiguredError() from error
    failed = True
    try:
        yield model
        failed = False
    finally:
        try:
            await client.aclose()
        except (httpx.HTTPError, GigaChatException, OSError) as error:
            if not failed:
                raise LLMUnavailableError() from error
            # Preserve the primary error, including cancellation and programming bugs.
            logger.warning("Cannot close LLM client after a failed operation")
