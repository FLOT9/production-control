from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.data.models import WebhookDelivery
from src.data.repositories.base_repository import BaseRepository


class WebhookDeliveryRepository(
    BaseRepository[WebhookDelivery],
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WebhookDelivery)

    async def list_deliveries(
        self, *, offset: int, limit: int
    ) -> list[WebhookDelivery]:
        statement = (
            select(WebhookDelivery)
            .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def get_with_attempts(self, delivery_id: int) -> WebhookDelivery | None:
        statement = (
            select(WebhookDelivery)
            .where(WebhookDelivery.id == delivery_id)
            .options(selectinload(WebhookDelivery.attempt_history))
        )
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def claim_for_delivery(
        self,
        *,
        delivery_id: int,
        worker_id: str,
        lock_seconds: int = 60,
    ) -> WebhookDelivery | None:
        now = datetime.now(UTC)

        statement = (
            update(WebhookDelivery)
            .where(
                WebhookDelivery.id == delivery_id,
                WebhookDelivery.status.in_(("pending", "retrying")),
                or_(
                    WebhookDelivery.next_attempt_at.is_(None),
                    WebhookDelivery.next_attempt_at <= now,
                ),
                or_(
                    WebhookDelivery.locked_until.is_(None),
                    WebhookDelivery.locked_until <= now,
                ),
            )
            .values(
                locked_by=worker_id,
                locked_until=now + timedelta(seconds=lock_seconds),
            )
            .returning(WebhookDelivery)
            .execution_options(populate_existing=True)
        )

        result = await self.session.execute(statement)
        return result.scalar_one_or_none()

    async def list_ready_for_dispatch(
        self,
        *,
        limit: int = 100,
    ) -> list[int]:
        now = datetime.now(UTC)

        statement = (
            select(WebhookDelivery.id)
            .where(
                WebhookDelivery.status.in_(("pending", "retrying")),
                or_(
                    WebhookDelivery.next_attempt_at.is_(None),
                    WebhookDelivery.next_attempt_at <= now,
                ),
                or_(
                    WebhookDelivery.locked_until.is_(None),
                    WebhookDelivery.locked_until <= now,
                ),
            )
            .order_by(WebhookDelivery.created_at, WebhookDelivery.id)
            .limit(limit)
        )

        result = await self.session.execute(statement)
        return list(result.scalars().all())

    async def list_by_subscription(
        self, subscription_id: int, *, offset: int, limit: int
    ) -> tuple[list[WebhookDelivery], int]:
        condition = WebhookDelivery.subscription_id == subscription_id
        total = await self.session.scalar(
            select(func.count()).select_from(WebhookDelivery).where(condition)
        )
        result = await self.session.execute(
            select(WebhookDelivery)
            .where(condition)
            .order_by(WebhookDelivery.created_at.desc(), WebhookDelivery.id.desc())
            .offset(offset)
            .limit(limit)
        )
        return list(result.scalars().all()), int(total or 0)
