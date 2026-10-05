from sqlalchemy.ext.asyncio import AsyncSession

from src.data.repositories.analytics_repository import AnalyticsRepository
from src.data.repositories.batch_repository import BatchRepository
from src.data.repositories.dashboard_repository import DashboardRepository
from src.data.repositories.product_repository import ProductRepository
from src.data.repositories.production_summary_repository import (
    ProductionSummaryRepository,
)
from src.data.repositories.webhook_delivery_attempt_repository import (
    WebhookDeliveryAttemptRepository,
)
from src.data.repositories.webhook_delivery_repository import (
    WebhookDeliveryRepository,
)
from src.data.repositories.webhook_subscription_repository import (
    WebhookSubscriptionRepository,
)
from src.data.repositories.work_center_repository import (
    WorkCenterRepository,
)


class UnitOfWork:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.work_centers = WorkCenterRepository(session)
        self.batches = BatchRepository(session)
        self.analytics = AnalyticsRepository(session)
        self.dashboard = DashboardRepository(session)
        self.products = ProductRepository(session)
        self.production_summaries = ProductionSummaryRepository(session)
        self.webhook_subscriptions = WebhookSubscriptionRepository(session)
        self.webhook_deliveries = WebhookDeliveryRepository(session)
        self.webhook_delivery_attempts = WebhookDeliveryAttemptRepository(session)

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()
