from typing import Annotated

from fastapi import APIRouter, Path, Query

from src.api.dependencies.webhooks import WebhookDeliveryHistoryServiceDep
from src.api.v1.schemas.webhook_delivery import (
    WebhookDeliveryDetails,
    WebhookDeliveryListItem,
)

router = APIRouter(prefix="/webhook-deliveries", tags=["webhook-deliveries"])


@router.get("", response_model=list[WebhookDeliveryListItem])
async def list_webhook_deliveries(
    service: WebhookDeliveryHistoryServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[WebhookDeliveryListItem]:
    deliveries = await service.list_deliveries(offset=offset, limit=limit)
    return [WebhookDeliveryListItem.model_validate(item) for item in deliveries]


@router.get("/{delivery_id}", response_model=WebhookDeliveryDetails)
async def get_webhook_delivery(
    delivery_id: Annotated[int, Path(gt=0)],
    service: WebhookDeliveryHistoryServiceDep,
) -> WebhookDeliveryDetails:
    delivery = await service.get_by_id(delivery_id)
    return WebhookDeliveryDetails.model_validate(delivery)
