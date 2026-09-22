import asyncio
from datetime import UTC, datetime
from math import ceil

from celery import Task

from src.application.services.webhook_delivery_service import WebhookDeliveryService
from src.core.database import async_session_maker, dispose_engine
from src.data.unit_of_work import UnitOfWork
from src.integrations.webhooks.http_client import WebhookHttpClient
from src.integrations.webhooks.signer import WebhookSigner
from src.tasks.celery_app import celery_app


async def _deliver_webhook(
    *,
    delivery_id: int,
    worker_id: str,
) -> dict[str, int | str | None]:
    try:
        async with async_session_maker() as session:
            service = WebhookDeliveryService(
                uow=UnitOfWork(session),
                signer=WebhookSigner(),
                http_client=WebhookHttpClient(),
            )
            delivery = await service.deliver(
                delivery_id=delivery_id,
                worker_id=worker_id,
            )

            if delivery is None:
                return {
                    "delivery_id": delivery_id,
                    "status": "skipped",
                    "next_attempt_at": None,
                    "retry_delay_seconds": None,
                }

            retry_delay_seconds = None

            if delivery.next_attempt_at is not None:
                retry_delay_seconds = max(
                    1,
                    ceil(
                        (delivery.next_attempt_at - datetime.now(UTC)).total_seconds()
                    ),
                )

            return {
                "delivery_id": delivery.id,
                "status": delivery.status,
                "next_attempt_at": (
                    delivery.next_attempt_at.isoformat()
                    if delivery.next_attempt_at is not None
                    else None
                ),
                "retry_delay_seconds": retry_delay_seconds,
            }
    finally:
        await dispose_engine()


@celery_app.task(
    bind=True,
    name="webhooks.deliver",
    max_retries=None,
)
def deliver_webhook(
    self: Task,
    delivery_id: int,
) -> dict[str, int | str | None]:
    worker_id = f"{self.request.hostname}:{self.request.id}"
    result = asyncio.run(
        _deliver_webhook(
            delivery_id=delivery_id,
            worker_id=worker_id,
        )
    )

    if result["status"] == "retrying":
        retry_delay_seconds = result["retry_delay_seconds"]
        countdown = retry_delay_seconds if isinstance(retry_delay_seconds, int) else 1
        raise self.retry(
            args=[delivery_id],
            countdown=countdown,
        )

    return result


async def _get_ready_delivery_ids(
    *,
    limit: int,
) -> list[int]:
    try:
        async with async_session_maker() as session:
            uow = UnitOfWork(session)
            return await uow.webhook_deliveries.list_ready_for_dispatch(
                limit=limit,
            )
    finally:
        await dispose_engine()


@celery_app.task(name="webhooks.dispatch")
def dispatch_webhooks(
    limit: int = 100,
) -> dict[str, int | list[int]]:
    delivery_ids = asyncio.run(_get_ready_delivery_ids(limit=limit))

    for delivery_id in delivery_ids:
        deliver_webhook.delay(delivery_id)

    return {
        "dispatched": len(delivery_ids),
        "delivery_ids": delivery_ids,
    }
