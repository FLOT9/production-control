from typing import Annotated

from fastapi import Depends

from src.application.services.webhook_delivery_history_service import (
    WebhookDeliveryHistoryService,
)
from src.application.services.webhook_subscription_service import (
    WebhookSubscriptionService,
)
from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork


async def get_webhook_subscription_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> WebhookSubscriptionService:
    return WebhookSubscriptionService(uow)


WebhookSubscriptionServiceDep = Annotated[
    WebhookSubscriptionService,
    Depends(get_webhook_subscription_service),
]


async def get_webhook_delivery_history_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> WebhookDeliveryHistoryService:
    return WebhookDeliveryHistoryService(uow)


WebhookDeliveryHistoryServiceDep = Annotated[
    WebhookDeliveryHistoryService,
    Depends(get_webhook_delivery_history_service),
]
