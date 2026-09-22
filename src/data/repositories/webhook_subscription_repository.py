from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import WebhookSubscription
from src.data.repositories.base_repository import BaseRepository


class WebhookSubscriptionRepository(
    BaseRepository[WebhookSubscription],
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WebhookSubscription)

    async def list_all(self) -> list[WebhookSubscription]:
        statement = select(WebhookSubscription).order_by(WebhookSubscription.id)
        result = await self.session.execute(statement)

        return list(result.scalars().all())

    async def find_active_by_event(
        self,
        event_type: str,
    ) -> list[WebhookSubscription]:
        statement = select(WebhookSubscription).where(
            WebhookSubscription.is_active.is_(True),
            WebhookSubscription.events.any(event_type),
        )

        result = await self.session.execute(statement)

        return list(result.scalars().all())
