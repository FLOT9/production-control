from datetime import UTC, datetime, timedelta
from time import time

from src.application.exceptions import (
    WebhookDeliveryNotFoundError,
    WebhookSubscriptionNotFoundError,
)
from src.data.models import WebhookDelivery, WebhookSubscription
from src.data.unit_of_work import UnitOfWork
from src.integrations.webhooks.exceptions import WebhookHttpError
from src.integrations.webhooks.http_client import WebhookHttpClient, WebhookHttpResponse
from src.integrations.webhooks.signer import WebhookSigner


class WebhookDeliveryService:
    RETRY_BASE_DELAY_SECONDS = 60

    def __init__(
        self,
        uow: UnitOfWork,
        signer: WebhookSigner,
        http_client: WebhookHttpClient,
    ) -> None:
        self.uow = uow
        self.signer = signer
        self.http_client = http_client

    async def get_by_id(
        self,
        delivery_id: int,
    ) -> WebhookDelivery:
        delivery = await self.uow.webhook_deliveries.get_by_id(delivery_id)

        if delivery is None:
            raise WebhookDeliveryNotFoundError(delivery_id)

        return delivery

    def _build_headers(
        self,
        *,
        delivery: WebhookDelivery,
        secret_key: str,
    ) -> dict[str, str]:
        timestamp = str(int(time()))

        signature = self.signer.sign(
            secret_key=secret_key,
            timestamp=timestamp,
            body=delivery.request_body,
        )

        return {
            "X-Webhook-Id": str(delivery.id),
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": signature,
        }

    async def _get_subscription(
        self,
        delivery: WebhookDelivery,
    ) -> WebhookSubscription:
        subscription = await self.uow.webhook_subscriptions.get_by_id(
            delivery.subscription_id
        )

        if subscription is None:
            raise WebhookSubscriptionNotFoundError(delivery.subscription_id)

        return subscription

    async def _send_once(
        self,
        *,
        delivery: WebhookDelivery,
        subscription: WebhookSubscription,
    ) -> WebhookHttpResponse:
        headers = self._build_headers(
            delivery=delivery,
            secret_key=subscription.secret_key,
        )

        return await self.http_client.post(
            url=delivery.target_url,
            body=delivery.request_body,
            headers=headers,
            timeout_seconds=subscription.timeout_seconds,
        )

    async def _record_response(
        self,
        *,
        delivery: WebhookDelivery,
        response: WebhookHttpResponse,
    ) -> None:
        attempt_number = delivery.attempts + 1

        await self.uow.webhook_delivery_attempts.create(
            delivery_id=delivery.id,
            attempt_number=attempt_number,
            response_status=response.status_code,
            response_body=response.body,
            duration_ms=response.duration_ms,
        )

        delivery.attempts = attempt_number
        delivery.response_status = response.status_code
        delivery.response_body = response.body
        delivery.error_message = None

    async def _record_error(
        self,
        *,
        delivery: WebhookDelivery,
        error: WebhookHttpError,
    ) -> None:
        attempt_number = delivery.attempts + 1
        error_message = str(error)[:2000]

        await self.uow.webhook_delivery_attempts.create(
            delivery_id=delivery.id,
            attempt_number=attempt_number,
            response_status=None,
            response_body=None,
            duration_ms=error.duration_ms,
            error_message=error_message,
        )

        delivery.attempts = attempt_number
        delivery.response_status = None
        delivery.response_body = None
        delivery.error_message = error_message

    @staticmethod
    def _release_lock(delivery: WebhookDelivery) -> None:
        delivery.locked_by = None
        delivery.locked_until = None

    def _schedule_retry(self, delivery: WebhookDelivery) -> None:
        delay_seconds = self.RETRY_BASE_DELAY_SECONDS * 2 ** (delivery.attempts - 1)
        delivery.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)

    async def deliver(
        self,
        delivery_id: int,
        worker_id: str,
    ) -> WebhookDelivery | None:
        delivery = await self.uow.webhook_deliveries.claim_for_delivery(
            delivery_id=delivery_id,
            worker_id=worker_id,
        )

        if delivery is None:
            return None

        await self.uow.commit()

        subscription = await self._get_subscription(delivery)

        if not subscription.is_active:
            delivery.status = "failed"
            delivery.error_message = "Webhook subscription is inactive"
            delivery.next_attempt_at = None
            self._release_lock(delivery)
            await self.uow.commit()
            return delivery

        try:
            response = await self._send_once(
                delivery=delivery,
                subscription=subscription,
            )
        except WebhookHttpError as error:
            await self._record_error(
                delivery=delivery,
                error=error,
            )

            if delivery.attempts <= subscription.retry_count:
                delivery.status = "retrying"
                self._schedule_retry(delivery)
            else:
                delivery.status = "failed"
                delivery.next_attempt_at = None

            self._release_lock(delivery)
            await self.uow.commit()
            return delivery

        await self._record_response(
            delivery=delivery,
            response=response,
        )

        if 200 <= response.status_code < 300:
            delivery.status = "delivered"
            delivery.delivered_at = datetime.now(UTC)
            delivery.next_attempt_at = None
        elif (
            response.status_code in {408, 429} or response.status_code >= 500
        ) and delivery.attempts <= subscription.retry_count:
            delivery.status = "retrying"
            self._schedule_retry(delivery)
        else:
            delivery.status = "failed"
            delivery.next_attempt_at = None

        self._release_lock(delivery)
        await self.uow.commit()
        return delivery
