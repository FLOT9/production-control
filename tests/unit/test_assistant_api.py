import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from pydantic import SecretStr

from src.api.exception_handlers import register_exception_handlers
from src.api.v1.routers.assistant import router
from src.core.config import settings
from src.domain.exceptions.batch import BatchNotFoundError


class AssistantApiTests(TestCase):
    def setUp(self):
        self.entered = False
        self.exited = False
        self.read = AsyncMock(
            return_value=SimpleNamespace(
                total_products=10,
                aggregated_products=8,
                pending_products=2,
            )
        )

        @asynccontextmanager
        async def statistics_service():
            self.entered = True
            try:
                yield SimpleNamespace(get_statistics=self.read)
            finally:
                self.exited = True

        self.bound = Mock()
        self.bound.ainvoke = AsyncMock(
            return_value=AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_batch_statistics",
                        "args": {"batch_id": 1},
                        "id": "call-1",
                        "type": "tool_call",
                    }
                ],
            )
        )
        self.model = Mock()
        self.model.bind_tools.return_value = self.bound
        self.model._client.aclose = AsyncMock()
        for target, value in (
            ("assistant_api_key", SecretStr("client-test-key")),
            ("gigachat_auth_key", SecretStr("provider-test-key")),
        ):
            p = patch.object(settings, target, value)
            p.start()
            self.addCleanup(p.stop)
        for target, kwargs in (
            (
                "src.integrations.llm.factory.GigaChat",
                {"return_value": self.model},
            ),
            (
                "src.api.dependencies.assistant.batch_analytics_service",
                {"new": statistics_service},
            ),
        ):
            p = patch(target, **kwargs)
            value = p.start()
            if target.endswith("GigaChat"):
                self.create_model = value
            self.addCleanup(p.stop)
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(router, prefix="/api/v1")
        self.client = TestClient(app)
        self.addCleanup(self.client.close)
        self.headers = {"X-API-Key": "client-test-key"}

    def ask(self, payload=None, headers=None):
        return self.client.post(
            "/api/v1/assistant/ask",
            headers=self.headers if headers is None else headers,
            json={"question": "ID 1?"} if payload is None else payload,
        )

    def test_success_and_resources_closed(self):
        response = self.ask({"question": "  ID 1?  "})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "answered")
        self.assertEqual(
            data["data"], {"batch_id": 1, "total": 10, "aggregated": 8, "remaining": 2}
        )
        self.assertTrue(self.entered and self.exited)
        self.assertEqual(self.bound.ainvoke.call_args.args[0][-1].content, "ID 1?")
        self.model._client.aclose.assert_awaited_once()

    def test_database_context_is_not_open_during_model_request(self):
        reply = self.bound.ainvoke.return_value

        async def choose_tool(_messages):
            self.assertFalse(self.entered)
            return reply

        self.bound.ainvoke.side_effect = choose_tool
        self.assertEqual(self.ask().status_code, 200)
        self.assertTrue(self.exited)

    def test_wrong_or_missing_key_does_not_create_model(self):
        for headers in ({}, {"X-API-Key": "wrong"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.ask(headers=headers).status_code, 401)
        self.create_model.assert_not_called()
        self.bound.ainvoke.assert_not_awaited()

    def test_invalid_questions_do_not_call_model(self):
        for payload in (
            {},
            {"question": "  "},
            {"question": "a" * 2001},
            {"question": 123},
            {"question": "ID 1?", "model": "other"},
        ):
            with self.subTest(payload=payload):
                self.assertEqual(self.ask(payload).status_code, 422)
        self.bound.ainvoke.assert_not_awaited()
        self.assertFalse(self.entered)

    def test_missing_configuration(self):
        for name in ("assistant_api_key", "gigachat_auth_key"):
            with self.subTest(name=name), patch.object(settings, name, None):
                self.assertEqual(self.ask().status_code, 503)
        self.create_model.assert_not_called()

    def test_missing_batch_is_domain_result(self):
        self.read.side_effect = BatchNotFoundError(1)
        response = self.ask()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "not_found")
        self.assertIsNone(response.json()["data"])
        self.assertTrue(self.exited)

    def test_unverified_text_is_not_exposed(self):
        self.bound.ainvoke.return_value = AIMessage(content="Осталось 999 изделий.")
        response = self.ask()
        self.assertEqual(response.json()["status"], "insufficient_data")
        self.assertNotIn("999", response.text)
        self.read.assert_not_awaited()

    def test_provider_failure_is_sanitized(self):
        self.bound.ainvoke.side_effect = httpx.ConnectError("private provider details")
        response = self.ask()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", response.text)
        self.model._client.aclose.assert_awaited_once()

    def test_timeout(self):
        self.bound.ainvoke.side_effect = httpx.ReadTimeout("private timeout")
        self.assertEqual(self.ask().status_code, 504)

    def test_total_deadline(self):
        async def slow_model(_messages):
            await asyncio.sleep(1)

        self.bound.ainvoke.side_effect = slow_model
        with patch.object(settings, "assistant_timeout_seconds", 0.01):
            self.assertEqual(self.ask().status_code, 504)
        self.model._client.aclose.assert_awaited_once()

    def test_programming_errors_are_not_mapped_to_503(self):
        for error in (ValueError("programming bug"), TypeError("programming bug")):
            with self.subTest(error=error):
                self.bound.ainvoke.side_effect = error
                with self.assertRaises(type(error)) as raised:
                    self.ask()
                self.assertIs(raised.exception, error)

    def test_invalid_model_arguments_are_mapped_to_503(self):
        self.bound.ainvoke.return_value.tool_calls[0]["args"]["batch_id"] = -1
        response = self.ask()
        self.assertEqual(response.status_code, 503)
        self.read.assert_not_awaited()

    def test_route_registered_and_schema_has_auth(self):
        from src.main import app

        with patch.object(settings, "gigachat_auth_key", None):
            schema = app.openapi()
        operation = schema["paths"]["/api/v1/assistant/ask"]["post"]
        self.assertIn("security", operation)
