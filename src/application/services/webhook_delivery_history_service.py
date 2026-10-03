from src.application.exceptions import (
    WebhookDeliveryNotFoundError,
    WebhookSubscriptionNotFoundError,
)
from src.data.models import WebhookDelivery
from src.data.unit_of_work import UnitOfWork


class WebhookDeliveryHistoryService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def list_deliveries(
        self, *, offset: int, limit: int
    ) -> list[WebhookDelivery]:
        return await self.uow.webhook_deliveries.list_deliveries(
            offset=offset, limit=limit
        )

    async def get_by_id(self, delivery_id: int) -> WebhookDelivery:
        delivery = await self.uow.webhook_deliveries.get_with_attempts(delivery_id)
        if delivery is None:
            raise WebhookDeliveryNotFoundError(delivery_id)
        return delivery

    async def list_subscription_deliveries(
        self, subscription_id: int, *, offset: int, limit: int
    ) -> tuple[list[WebhookDelivery], int]:
        if await self.uow.webhook_subscriptions.get_by_id(subscription_id) is None:
            raise WebhookSubscriptionNotFoundError(subscription_id)
        return await self.uow.webhook_deliveries.list_by_subscription(
            subscription_id, offset=offset, limit=limit
        )
