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

        self.search_read = AsyncMock(
            return_value=(
                [
                    {
                        "id": 101,
                        "batch_number": 41,
                        "batch_date": "2026-11-10",
                        "work_center_id": 7,
                        "is_closed": False,
                    },
                ],
                2,
            )
        )

        @asynccontextmanager
        async def search_service():
            yield SimpleNamespace(list_batches=self.search_read)

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
            ("assistant_local_enabled", False),
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
                "src.api.dependencies.assistant.batch_search_service",
                {"new": search_service},
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
        self.app = app
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

    def test_local_mode_accepts_loopback_without_client_key(self):
        with (
            patch.object(settings, "assistant_local_enabled", True),
            patch.object(settings, "assistant_api_key", None),
            TestClient(
                self.app, base_url="http://127.0.0.1", client=("127.0.0.1", 50000)
            ) as client,
        ):
            response = client.post("/api/v1/assistant/ask", json={"question": "ID 1?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "answered")

    def test_local_mode_does_not_bypass_key_for_external_peer_or_host(self):
        for peer, origin in (
            ("192.0.2.10", "http://127.0.0.1"),
            ("127.0.0.1", "http://external.example"),
        ):
            with (
                self.subTest(peer=peer, origin=origin),
                patch.object(settings, "assistant_local_enabled", True),
                TestClient(self.app, base_url=origin, client=(peer, 50000)) as client,
            ):
                response = client.post(
                    "/api/v1/assistant/ask", json={"question": "ID 1?"}
                )
                self.assertEqual(response.status_code, 401)
        self.create_model.assert_not_called()

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

    def test_search_result_is_serialized_and_all_tools_are_bound(self):
        self.bound.ainvoke.return_value = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "find_batches",
                    "args": {"batch_number": 41, "limit": 1},
                    "id": "find-call",
                    "type": "tool_call",
                }
            ],
        )
        response = self.ask({"question": "Найди партию №41"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "needs_clarification")
        self.assertEqual(data["search"]["total"], 2)
        self.assertEqual(data["search"]["items"][0]["batch_date"], "2026-11-10")
        self.assertIsNone(data["data"])
        self.assertEqual(data["tools_called"], ["find_batches"])
        self.assertEqual(
            {tool.name for tool in self.model.bind_tools.call_args.args[0]},
            {"get_batch_statistics", "find_batches", "compare_batches"},
        )

    def test_comparison_uses_database_metrics_for_each_requested_batch(self):
        compare = AsyncMock(
            return_value=SimpleNamespace(
                items=[
                    SimpleNamespace(
                        batch_info=SimpleNamespace(id=batch_id),
                        total_products=10,
                        aggregated_products=10 - pending,
                        pending_products=pending,
                        aggregation_percent=(10 - pending) * 10,
                        products_per_hour=1.0,
                    )
                    for batch_id, pending in [(1, 2), (2, 4)]
                ]
            )
        )

        @asynccontextmanager
        async def comparison_service():
            yield SimpleNamespace(compare=compare)

        self.bound.ainvoke.return_value = AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "compare_batches",
                    "args": {"batch_ids": [1, 2]},
                    "id": "compare-call",
                    "type": "tool_call",
                }
            ],
        )
        with patch(
            "src.api.dependencies.assistant.batch_comparison_service",
            new=comparison_service,
        ):
            response = self.ask({"question": "Сравни остатки в партиях с ID 1 и 2"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "answered")
        self.assertEqual(data["tools_called"], ["compare_batches"])
        first, second = data["answer"].splitlines()
        self.assertIn("ID 1: всего 10 изд., агрегировано 8, осталось 2", first)
        self.assertIn("ID 2: всего 10 изд., агрегировано 6, осталось 4", second)
        compare.assert_awaited_once_with([1, 2])
        self.read.assert_not_awaited()
