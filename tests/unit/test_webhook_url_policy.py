import asyncio
import socket
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.dependencies.webhooks import get_webhook_subscription_service
from src.api.exception_handlers import register_exception_handlers
from src.api.v1.routers.webhooks import legacy_router, router
from src.api.v1.schemas.webhook import (
    WebhookSubscriptionUpdate,
)
from src.application.services.webhook_subscription_service import (
    WebhookSubscriptionService,
)
from src.integrations.webhooks.exceptions import WebhookHttpError
from src.integrations.webhooks.http_client import WebhookHttpClient
from src.integrations.webhooks.url_policy import UnsafeWebhookUrlError, resolve_target


def answers(*ips):
    return [
        (
            socket.AF_INET6 if ":" in ip else socket.AF_INET,
            socket.SOCK_STREAM,
            6,
            "",
            (ip, 443),
        )
        for ip in ips
    ]


def mock_http_client(handler):
    original_client = httpx.AsyncClient

    def client(**kwargs):
        assert kwargs == {"follow_redirects": False, "trust_env": False}
        return original_client(transport=httpx.MockTransport(handler), **kwargs)

    return client


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/hook",
        "http://10.0.0.1",
        "http://169.254.169.254",
        "http://192.168.1.1",
        "http://0.0.0.0",
        "http://224.0.0.1",
        "http://localhost./",
        "http://[::1]",
        "http://[fc00::1]",
        "http://[fec0::1]",
        "http://[::ffff:127.0.0.1]",
        "http://[64:ff9b::a00:1]",
        "http://[2002:a00:1::]",
        "http://192.0.0.8",
        "http://user:password@example.com",
        "http://2130706433",
        "http://127.1",
    ],
)
def test_unsafe_literal_rejected_at_schema_or_dns_boundary(url):
    async def scenario():
        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                return_value=answers("127.0.0.1"),
            ),
            pytest.raises((UnsafeWebhookUrlError, ValidationError)),
        ):
            request = WebhookSubscriptionUpdate(url=url)
            await resolve_target(str(request.url))

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "ips", [("93.184.216.34", "10.0.0.1"), ("::1",), ("fec0::1",), ("192.168.1.1",)]
)
def test_domain_with_any_private_answer_is_blocked_before_storage_or_http(ips):
    async def scenario():
        uow = SimpleNamespace(
            webhook_subscriptions=SimpleNamespace(
                create=AsyncMock(), get_by_id=AsyncMock()
            ),
            commit=AsyncMock(),
        )
        service = WebhookSubscriptionService(uow)
        with patch(
            "src.integrations.webhooks.url_policy.socket.getaddrinfo",
            return_value=answers(*ips),
        ):
            with pytest.raises(UnsafeWebhookUrlError):
                await service.create(
                    url="https://example.com/hook",
                    events=[],
                    secret_key="x" * 32,
                    retry_count=0,
                    timeout_seconds=10,
                )
            with pytest.raises(UnsafeWebhookUrlError):
                await service.update(1, {"url": "https://example.com/hook"})
            with patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient"
            ) as transport:
                with pytest.raises(WebhookHttpError):
                    await WebhookHttpClient().post(
                        url="https://example.com/hook",
                        body=b"{}",
                        headers={},
                        timeout_seconds=10,
                    )
                transport.assert_not_called()
        uow.webhook_subscriptions.create.assert_not_awaited()
        uow.commit.assert_not_awaited()

    asyncio.run(scenario())


def test_public_target_is_pinned_host_and_sni_preserved_redirect_not_followed():
    async def scenario():
        captured = []

        def handler(request):
            captured.append(request)
            return httpx.Response(
                302, headers={"Location": "http://127.0.0.1/private"}, text="redirect"
            )

        original_client = httpx.AsyncClient

        def client(**kwargs):
            assert kwargs == {"follow_redirects": False, "trust_env": False}
            return original_client(transport=httpx.MockTransport(handler), **kwargs)

        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                side_effect=[answers("93.184.216.34"), answers("127.0.0.1")],
            ) as resolver,
            patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient",
                side_effect=client,
            ),
        ):
            result = await WebhookHttpClient().post(
                url="https://example.com:8443/hook?x=1",
                body=b'{"a":1}',
                headers={"X-Webhook-Signature": "sig"},
                timeout_seconds=10,
            )
            assert result.status_code == 302
            resolver.assert_called_once()
        assert len(captured) == 1
        request = captured[0]
        assert request.url.host == "93.184.216.34"
        assert request.url.port == 8443
        assert request.url.path == "/hook"
        assert request.headers["host"] == "example.com:8443"
        assert request.extensions["sni_hostname"] == "example.com"
        assert request.headers["X-Webhook-Signature"] == "sig"
        assert request.content == b'{"a":1}'

    asyncio.run(scenario())


@pytest.mark.parametrize("error_type", [httpx.ConnectError, httpx.ConnectTimeout])
def test_connect_failure_uses_next_validated_ip_without_resolving_again(error_type):
    async def scenario():
        captured = []

        def handler(request):
            captured.append(request)
            if request.url.host == "2606:4700:4700::1111":
                raise error_type("IPv6 unavailable", request=request)
            return httpx.Response(204)

        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                side_effect=[
                    answers("2606:4700:4700::1111", "93.184.216.34"),
                    answers("127.0.0.1"),
                ],
            ) as resolver,
            patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient",
                side_effect=mock_http_client(handler),
            ),
        ):
            response = await WebhookHttpClient().post(
                url="https://example.com:8443/hook?x=1",
                body=b'{"a":1}',
                headers={"X-Webhook-Signature": "sig"},
                timeout_seconds=10,
            )
        assert response.status_code == 204
        resolver.assert_called_once()
        assert [request.url.host for request in captured] == [
            "2606:4700:4700::1111",
            "93.184.216.34",
        ]
        for request in captured:
            assert request.url.port == 8443
            assert request.url.path == "/hook"
            assert request.url.query == b"x=1"
            assert request.headers["host"] == "example.com:8443"
            assert request.extensions["sni_hostname"] == "example.com"
            assert request.headers["X-Webhook-Signature"] == "sig"
            assert request.content == b'{"a":1}'
            assert request.extensions["timeout"]["connect"] == 5

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "error_type",
    [
        httpx.ReadError,
        httpx.ReadTimeout,
        httpx.WriteError,
        httpx.WriteTimeout,
        httpx.RemoteProtocolError,
        httpx.PoolTimeout,
    ],
)
def test_other_transport_errors_do_not_send_to_next_ip(error_type):
    async def scenario():
        captured = []

        def handler(request):
            captured.append(request)
            raise error_type("Request might already be delivered", request=request)

        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                return_value=answers("2606:4700:4700::1111", "93.184.216.34"),
            ),
            patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient",
                side_effect=mock_http_client(handler),
            ),
            pytest.raises(WebhookHttpError) as raised,
        ):
            await WebhookHttpClient().post(
                url="https://example.com/hook",
                body=b"{}",
                headers={},
                timeout_seconds=10,
            )
        assert isinstance(raised.value.__cause__, error_type)
        assert len(captured) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("status_code", [204, 302, 400, 500])
def test_http_response_stops_ip_fallback(status_code):
    async def scenario():
        captured = []

        def handler(request):
            captured.append(request)
            return httpx.Response(status_code)

        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                return_value=answers("2606:4700:4700::1111", "93.184.216.34"),
            ),
            patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient",
                side_effect=mock_http_client(handler),
            ),
        ):
            response = await WebhookHttpClient().post(
                url="https://example.com/hook",
                body=b"{}",
                headers={},
                timeout_seconds=10,
            )
        assert response.status_code == status_code
        assert len(captured) == 1

    asyncio.run(scenario())


def test_all_connection_failures_are_reported_as_one_delivery_error():
    async def scenario():
        captured = []

        def handler(request):
            captured.append(request)
            raise httpx.ConnectError(
                f"Unavailable: {request.url.host}", request=request
            )

        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                return_value=answers("2606:4700:4700::1111", "93.184.216.34"),
            ),
            patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient",
                side_effect=mock_http_client(handler),
            ),
            pytest.raises(WebhookHttpError) as raised,
        ):
            await WebhookHttpClient().post(
                url="https://example.com/hook",
                body=b"{}",
                headers={},
                timeout_seconds=10,
            )
        assert len(captured) == 2
        assert isinstance(raised.value.__cause__, httpx.ConnectError)
        assert "93.184.216.34" in str(raised.value)
        assert raised.value.duration_ms >= 0

    asyncio.run(scenario())


def test_overall_timeout_after_sending_body_does_not_try_another_ip():
    async def scenario():
        captured = []

        async def handler(request):
            captured.append(request)
            await asyncio.sleep(2)
            return httpx.Response(204)

        with (
            patch(
                "src.integrations.webhooks.url_policy.socket.getaddrinfo",
                return_value=answers("2606:4700:4700::1111", "93.184.216.34"),
            ),
            patch(
                "src.integrations.webhooks.http_client.httpx.AsyncClient",
                side_effect=mock_http_client(handler),
            ),
            pytest.raises(WebhookHttpError) as raised,
        ):
            await WebhookHttpClient().post(
                url="https://example.com/hook",
                body=b"{}",
                headers={},
                timeout_seconds=1,
            )
        assert isinstance(raised.value.__cause__, TimeoutError)
        assert len(captured) == 1
        assert captured[0].content == b"{}"

    asyncio.run(scenario())


def test_create_and_update_routes_reject_private_urls_with_422():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    app.include_router(legacy_router, prefix="/api/v1")
    register_exception_handlers(app)
    service = AsyncMock()
    app.dependency_overrides[get_webhook_subscription_service] = lambda: service
    with TestClient(app) as client:
        for prefix in ("webhooks", "webhook-subscriptions"):
            response = client.post(
                f"/api/v1/{prefix}",
                json={
                    "url": "http://127.0.0.1",
                    "events": ["batch_created"],
                    "secret_key": "x" * 32,
                },
            )
            assert response.status_code == 422
            assert (
                client.patch(
                    f"/api/v1/{prefix}/1", json={"url": "http://10.0.0.1"}
                ).status_code
                == 422
            )
    assert service.mock_calls == []


def test_dns_failure_maps_to_422_at_api_boundary():
    app = FastAPI()
    app.include_router(router, prefix="/api/v1")
    register_exception_handlers(app)
    uow = SimpleNamespace(webhook_subscriptions=SimpleNamespace(create=AsyncMock()))
    app.dependency_overrides[get_webhook_subscription_service] = lambda: (
        WebhookSubscriptionService(uow)
    )
    with (
        patch(
            "src.integrations.webhooks.url_policy.socket.getaddrinfo",
            side_effect=socket.gaierror(),
        ),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/v1/webhooks",
            json={
                "url": "https://example.com",
                "events": ["batch_created"],
                "secret_key": "x" * 32,
            },
        )
        assert response.status_code == 422
    uow.webhook_subscriptions.create.assert_not_awaited()
