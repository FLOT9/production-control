import json

from src.application.events import WebhookEvent
from src.data.unit_of_work import UnitOfWork


class WebhookEventService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def create_deliveries(
        self,
        event: WebhookEvent,
    ) -> list[int]:
        subscriptions = await self.uow.webhook_subscriptions.find_active_by_event(
            event.event_type.value
        )

        payload = {
            "event_id": str(event.event_id),
            "event": event.event_type.value,
            "timestamp": event.occurred_at.isoformat(),
            "data": event.data,
        }
        request_body = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        delivery_ids: list[int] = []

        for subscription in subscriptions:
            delivery = await self.uow.webhook_deliveries.create(
                event_id=event.event_id,
                subscription_id=subscription.id,
                event_type=event.event_type.value,
                payload=payload,
                target_url=subscription.url,
                request_body=request_body,
            )
            delivery_ids.append(delivery.id)

        return delivery_ids
