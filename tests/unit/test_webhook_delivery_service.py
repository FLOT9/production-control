import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.application.services.webhook_delivery_service import WebhookDeliveryService
from src.integrations.webhooks.exceptions import WebhookHttpError
from src.integrations.webhooks.http_client import WebhookHttpResponse
from src.integrations.webhooks.signer import WebhookSigner


@pytest.mark.parametrize(
    "status,expected",
    [(204, "delivered"), (400, "failed"), (429, "retrying"), (503, "retrying")],
)
def test_delivery_records_response_releases_lock_and_commits(status, expected):
    async def scenario():
        delivery = SimpleNamespace(
            id=1,
            subscription_id=2,
            target_url="https://example.com/hook",
            request_body=b"{}",
            attempts=0,
            locked_by="worker",
            locked_until=object(),
            next_attempt_at=None,
            delivered_at=None,
        )
        subscription = SimpleNamespace(
            is_active=True, secret_key="secret", timeout_seconds=10, retry_count=3
        )
        uow = SimpleNamespace(
            webhook_deliveries=SimpleNamespace(
                claim_for_delivery=AsyncMock(return_value=delivery)
            ),
            webhook_subscriptions=SimpleNamespace(
                get_by_id=AsyncMock(return_value=subscription)
            ),
            webhook_delivery_attempts=SimpleNamespace(create=AsyncMock()),
            commit=AsyncMock(),
        )
        http = SimpleNamespace(
            post=AsyncMock(return_value=WebhookHttpResponse(status, "body", 7))
        )
        result = await WebhookDeliveryService(uow, WebhookSigner(), http).deliver(
            1, "worker"
        )
        assert result is delivery
        assert delivery.status == expected
        assert delivery.locked_by is delivery.locked_until is None
        assert delivery.attempts == 1
        assert uow.commit.await_count == 2
        assert (
            uow.webhook_delivery_attempts.create.await_args.kwargs["response_status"]
            == status
        )
        headers = http.post.await_args.kwargs["headers"]
        assert headers["X-Webhook-Id"] == "1"
        assert headers["X-Webhook-Signature"]
        if expected == "retrying":
            assert delivery.next_attempt_at is not None
        if expected == "delivered":
            assert delivery.delivered_at is not None

    asyncio.run(scenario())


@pytest.mark.parametrize("retries,expected", [(0, "failed"), (3, "retrying")])
def test_blocked_target_is_recorded_without_stuck_lock(retries, expected):
    async def scenario():
        delivery = SimpleNamespace(
            id=1,
            subscription_id=2,
            target_url="http://127.0.0.1",
            request_body=b"{}",
            attempts=0,
            locked_by="worker",
            locked_until=object(),
            next_attempt_at=None,
        )
        uow = SimpleNamespace(
            webhook_deliveries=SimpleNamespace(
                claim_for_delivery=AsyncMock(return_value=delivery)
            ),
            webhook_subscriptions=SimpleNamespace(
                get_by_id=AsyncMock(
                    return_value=SimpleNamespace(
                        is_active=True,
                        secret_key="secret",
                        timeout_seconds=10,
                        retry_count=retries,
                    )
                )
            ),
            webhook_delivery_attempts=SimpleNamespace(create=AsyncMock()),
            commit=AsyncMock(),
        )
        http = SimpleNamespace(
            post=AsyncMock(
                side_effect=WebhookHttpError(message="Unsafe target", duration_ms=1)
            )
        )
        await WebhookDeliveryService(uow, WebhookSigner(), http).deliver(1, "worker")
        assert delivery.status == expected
        assert delivery.locked_by is delivery.locked_until is None
        assert delivery.error_message == "Unsafe target"
        assert delivery.attempts == 1
        assert uow.commit.await_count == 2

    asyncio.run(scenario())
