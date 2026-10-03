from src.application.events import WebhookEventType
from src.application.exceptions import WebhookSubscriptionNotFoundError
from src.data.models import WebhookSubscription
from src.data.unit_of_work import UnitOfWork

UPDATABLE_WEBHOOK_FIELDS = (
    "url",
    "events",
    "secret_key",
    "is_active",
    "retry_count",
    "timeout_seconds",
)


class WebhookSubscriptionService:
    def __init__(self, uow: UnitOfWork) -> None:
        self.uow = uow

    async def create(
        self,
        *,
        url: str,
        events: list[WebhookEventType],
        secret_key: str,
        retry_count: int,
        timeout_seconds: int,
    ) -> WebhookSubscription:
        subscription = await self.uow.webhook_subscriptions.create(
            url=url,
            events=[event.value for event in events],
            secret_key=secret_key,
            retry_count=retry_count,
            timeout_seconds=timeout_seconds,
        )
        await self.uow.commit()

        return subscription

    async def get_by_id(
        self,
        subscription_id: int,
    ) -> WebhookSubscription:
        subscription = await self.uow.webhook_subscriptions.get_by_id(subscription_id)
        if subscription is None:
            raise WebhookSubscriptionNotFoundError(subscription_id)

        return subscription

    async def list_all(self) -> list[WebhookSubscription]:
        return await self.uow.webhook_subscriptions.list_all()

    async def update(
        self,
        subscription_id: int,
        changes: dict[str, object],
    ) -> WebhookSubscription:
        subscription = await self.get_by_id(subscription_id)

        if not changes:
            return subscription

        for field_name in UPDATABLE_WEBHOOK_FIELDS:
            if field_name in changes:
                setattr(subscription, field_name, changes[field_name])

        await self.uow.commit()
        await self.uow.webhook_subscriptions.refresh(subscription)

        return subscription

    async def deactivate(
        self,
        subscription_id: int,
    ) -> None:
        subscription = await self.get_by_id(subscription_id)

        if not subscription.is_active:
            return

        subscription.is_active = False
        await self.uow.commit()

    async def list_page(
        self, *, offset: int, limit: int
    ) -> tuple[list[WebhookSubscription], int]:
        return await self.uow.webhook_subscriptions.list_page(
            offset=offset, limit=limit
        )
