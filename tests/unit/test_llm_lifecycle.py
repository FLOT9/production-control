import asyncio
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

import httpx
from pydantic import SecretStr

from src.application.ai.exceptions import (
    AssistantNotConfiguredError,
    LLMUnavailableError,
)
from src.core.config import Settings
from src.integrations.llm.factory import create_gigachat, gigachat_model


class LLMLifecycleTests(IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = Settings.model_construct(
            gigachat_auth_key=SecretStr("test-key")
        )
        self.model = Mock()
        self.model._client.aclose = AsyncMock()

    async def test_client_is_closed_and_sdk_retries_are_disabled(self):
        with patch(
            "src.integrations.llm.factory.GigaChat", return_value=self.model
        ) as constructor:
            async with gigachat_model(self.settings) as model:
                self.assertIs(model, self.model)
                self.model._client.aclose.assert_not_awaited()
            self.model._client.aclose.assert_awaited_once()
            self.assertEqual(constructor.call_args.kwargs["max_retries"], 0)

    async def test_cancellation_closes_client(self):
        with (
            patch("src.integrations.llm.factory.GigaChat", return_value=self.model),
            self.assertRaises(asyncio.CancelledError),
        ):
            async with gigachat_model(self.settings):
                raise asyncio.CancelledError()
        self.model._client.aclose.assert_awaited_once()

    async def test_close_failure_does_not_replace_primary_error(self):
        self.model._client.aclose.side_effect = httpx.ConnectError("close failed")
        error = ValueError("original bug")
        with (
            patch("src.integrations.llm.factory.GigaChat", return_value=self.model),
            self.assertRaises(ValueError) as raised,
        ):
            async with gigachat_model(self.settings):
                raise error
        self.assertIs(raised.exception, error)

    async def test_close_failure_after_success_is_translated(self):
        self.model._client.aclose.side_effect = httpx.ConnectError(
            "private close error"
        )
        with (
            patch("src.integrations.llm.factory.GigaChat", return_value=self.model),
            self.assertRaises(LLMUnavailableError) as raised,
        ):
            async with gigachat_model(self.settings):
                pass
        self.assertNotIn("private", str(raised.exception))

    async def test_missing_credentials_do_not_construct_sdk(self):
        for key in (None, SecretStr("")):
            with self.subTest(key_present=key is not None):
                self.settings.gigachat_auth_key = key
                with patch("src.integrations.llm.factory.GigaChat") as constructor:
                    with self.assertRaises(AssistantNotConfiguredError):
                        async with gigachat_model(self.settings):
                            self.fail("Unconfigured model must not be yielded")
                    constructor.assert_not_called()

    async def test_factory_only_constructs_wrapper_without_initializing_sdk(self):
        model = create_gigachat(self.settings)
        self.assertNotIn("_client", model.__dict__)
        self.assertEqual(model.max_retries, 0)
