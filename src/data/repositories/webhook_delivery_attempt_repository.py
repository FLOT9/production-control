from sqlalchemy.ext.asyncio import AsyncSession

from src.data.models import WebhookDeliveryAttempt
from src.data.repositories.base_repository import BaseRepository


class WebhookDeliveryAttemptRepository(
    BaseRepository[WebhookDeliveryAttempt],
):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, WebhookDeliveryAttempt)
