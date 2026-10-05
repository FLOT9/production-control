import hashlib
import hmac
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api.dependencies.webhooks import (
    get_webhook_delivery_history_service,
    get_webhook_subscription_service,
)
from src.api.v1.routers.webhooks import legacy_router, router
from src.application.events import WebhookEvent, WebhookEventType
from src.application.exceptions import WebhookSubscriptionNotFoundError
from src.application.services.webhook_delivery_history_service import (
    WebhookDeliveryHistoryService,
)
from src.application.services.webhook_delivery_service import WebhookDeliveryService
from src.application.services.webhook_event_service import WebhookEventService
from src.integrations.webhooks.http_client import WebhookHttpResponse
from src.integrations.webhooks.signer import WebhookSigner
from tests.unit import test_batch_auto_close as auto_close_tests


class BatchChangeTests(IsolatedAsyncioTestCase):
    def setUp(self):
        auto_close_tests.AutoCloseServiceTests.setUp(self)

    async def test_only_actual_changes_and_dates_are_serialized(self):
        old_end = self.row.shift_end
        new_end = datetime(2026, 10, 3, tzinfo=UTC)
        await self.service.update(
            1, {"shift": "Night", "team": "A", "shift_end": new_end}
        )
        event = self.events.create_deliveries.await_args.args[0]
        self.assertEqual(event.event_type, WebhookEventType.BATCH_UPDATED)
        self.assertEqual(
            event.data["changes"],
            {
                "shift": {"old": "Day", "new": "Night"},
                "shift_end": {"old": old_end.isoformat(), "new": new_end.isoformat()},
            },
        )
        json.dumps(event.data)

    async def test_unchanged_values_do_not_emit_notification(self):
        await self.service.update(1, {"team": "A", "is_closed": False})
        self.events.create_deliveries.assert_not_awaited()
        self.uow.commit.assert_not_awaited()


class WebhookEventTests(IsolatedAsyncioTestCase):
    async def test_payload_is_saved_as_exact_utf8_bytes_before_commit(self):
        uow = SimpleNamespace(
            webhook_subscriptions=SimpleNamespace(
                find_active_by_event=AsyncMock(
                    return_value=[SimpleNamespace(id=9, url="https://example.com/hook")]
                )
            ),
            webhook_deliveries=SimpleNamespace(
                create=AsyncMock(return_value=SimpleNamespace(id=15))
            ),
            commit=AsyncMock(),
        )
        event = WebhookEvent(WebhookEventType.BATCH_UPDATED, {"name": "Партия"})
        self.assertEqual(await WebhookEventService(uow).create_deliveries(event), [15])
        saved = uow.webhook_deliveries.create.await_args.kwargs
        self.assertEqual(json.loads(saved["request_body"]), saved["payload"])
        self.assertEqual(
            set(saved["payload"]), {"event_id", "event", "timestamp", "data"}
        )
        self.assertEqual(saved["payload"]["event"], "batch_updated")
        uow.commit.assert_not_awaited()

    async def test_missing_subscription_does_not_query_deliveries(self):
        uow = SimpleNamespace(
            webhook_subscriptions=SimpleNamespace(
                get_by_id=AsyncMock(return_value=None)
            ),
            webhook_deliveries=SimpleNamespace(list_by_subscription=AsyncMock()),
        )
        with self.assertRaises(WebhookSubscriptionNotFoundError):
            await WebhookDeliveryHistoryService(uow).list_subscription_deliveries(
                123, offset=0, limit=20
            )
        uow.webhook_deliveries.list_by_subscription.assert_not_awaited()

    async def test_history_is_scoped_and_keeps_total(self):
        uow = SimpleNamespace(
            webhook_subscriptions=SimpleNamespace(
                get_by_id=AsyncMock(return_value=object())
            ),
            webhook_deliveries=SimpleNamespace(
                list_by_subscription=AsyncMock(return_value=([], 12))
            ),
        )
        self.assertEqual(
            await WebhookDeliveryHistoryService(uow).list_subscription_deliveries(
                9, offset=20, limit=5
            ),
            ([], 12),
        )
        uow.webhook_deliveries.list_by_subscription.assert_awaited_once_with(
            9, offset=20, limit=5
        )

    async def test_retry_preserves_body_event_id_and_signature_matches_wire_bytes(self):
        body = b'{"event":"batch_updated","event_id":"stable"}'
        delivery = SimpleNamespace(
            id=5,
            subscription_id=9,
            request_body=body,
            target_url="https://example.com",
            attempts=0,
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
            post=AsyncMock(
                side_effect=[
                    WebhookHttpResponse(500, "retry", 1),
                    WebhookHttpResponse(200, "ok", 1),
                ]
            )
        )
        service = WebhookDeliveryService(uow, WebhookSigner(), http)
        await service.deliver(5, "worker")
        self.assertEqual(delivery.status, "retrying")
        await service.deliver(5, "worker")
        self.assertEqual(delivery.status, "delivered")
        self.assertEqual(delivery.attempts, 2)
        for call in http.post.await_args_list:
            sent = call.kwargs
            self.assertEqual(sent["body"], body)
            timestamp = sent["headers"]["X-Webhook-Timestamp"]
            digest = hmac.new(
                b"secret", timestamp.encode() + b"." + body, hashlib.sha256
            ).hexdigest()
            self.assertEqual(sent["headers"]["X-Webhook-Signature"], "v1=" + digest)


class WebhookApiTests(TestCase):
    def test_pagination_new_routes_and_legacy_array(self):
        now = datetime.now(UTC)
        item = {
            "id": 9,
            "url": "https://example.com",
            "events": ["batch_updated"],
            "is_active": True,
            "retry_count": 3,
            "timeout_seconds": 10,
            "created_at": now,
            "updated_at": now,
        }

        subscriptions = SimpleNamespace(
            list_page=AsyncMock(return_value=([item], 4)),
            list_all=AsyncMock(return_value=[item]),
        )
        history = SimpleNamespace(
            list_subscription_deliveries=AsyncMock(return_value=([], 0))
        )
        app = FastAPI()
        app.include_router(router, prefix="/api/v1")
        app.include_router(legacy_router, prefix="/api/v1")
        app.dependency_overrides[get_webhook_subscription_service] = lambda: (
            subscriptions
        )
        app.dependency_overrides[get_webhook_delivery_history_service] = lambda: history
        with TestClient(app) as client:
            result = client.get("/api/v1/webhooks?offset=2&limit=1")
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()["total"], 4)
            self.assertEqual(len(result.json()["items"]), 1)
            subscriptions.list_page.assert_awaited_once_with(offset=2, limit=1)
            self.assertIsInstance(
                client.get("/api/v1/webhook-subscriptions").json(), list
            )
            self.assertEqual(
                client.get("/api/v1/webhooks/9/deliveries").json(),
                {"items": [], "total": 0},
            )
            history.list_subscription_deliveries.assert_awaited_once_with(
                9, offset=0, limit=20
            )
            self.assertEqual(client.get("/api/v1/webhooks?limit=101").status_code, 422)
            self.assertEqual(
                client.get("/api/v1/webhooks/0/deliveries").status_code, 422
            )
