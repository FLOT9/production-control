from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from src.api.dependencies.webhooks import (
    WebhookDeliveryHistoryServiceDep,
    WebhookSubscriptionServiceDep,
)
from src.api.v1.schemas import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)
from src.api.v1.schemas.webhook import WebhookSubscriptionPage
from src.api.v1.schemas.webhook_delivery import (
    WebhookDeliveryListItem,
    WebhookDeliveryPage,
)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
legacy_router = APIRouter(
    prefix="/webhook-subscriptions", tags=["webhook-subscriptions"]
)


@legacy_router.post(
    "",
    response_model=WebhookSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_webhook_subscription(
    payload: WebhookSubscriptionCreate,
    service: WebhookSubscriptionServiceDep,
) -> WebhookSubscriptionRead:
    subscription = await service.create(
        url=str(payload.url),
        events=payload.events,
        secret_key=payload.secret_key,
        retry_count=payload.retry_count,
        timeout_seconds=payload.timeout_seconds,
    )
    return WebhookSubscriptionRead.model_validate(subscription)


@legacy_router.get(
    "",
    response_model=list[WebhookSubscriptionRead],
)
async def list_webhook_subscriptions(
    service: WebhookSubscriptionServiceDep,
) -> list[WebhookSubscriptionRead]:
    subscriptions = await service.list_all()
    return [
        WebhookSubscriptionRead.model_validate(subscription)
        for subscription in subscriptions
    ]


@legacy_router.get(
    "/{subscription_id}",
    response_model=WebhookSubscriptionRead,
)
async def get_webhook_subscription(
    subscription_id: int,
    service: WebhookSubscriptionServiceDep,
) -> WebhookSubscriptionRead:
    subscription = await service.get_by_id(subscription_id)
    return WebhookSubscriptionRead.model_validate(subscription)


@legacy_router.patch(
    "/{subscription_id}",
    response_model=WebhookSubscriptionRead,
)
async def update_webhook_subscription(
    subscription_id: int,
    payload: WebhookSubscriptionUpdate,
    service: WebhookSubscriptionServiceDep,
) -> WebhookSubscriptionRead:
    subscription = await service.update(
        subscription_id,
        payload.model_dump(exclude_unset=True, mode="json"),
    )
    return WebhookSubscriptionRead.model_validate(subscription)


@legacy_router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deactivate_webhook_subscription(
    subscription_id: int,
    service: WebhookSubscriptionServiceDep,
) -> None:
    await service.deactivate(subscription_id)


router.add_api_route(
    "",
    create_webhook_subscription,
    methods=["POST"],
    response_model=WebhookSubscriptionRead,
    status_code=status.HTTP_201_CREATED,
)


router.add_api_route(
    "/{subscription_id}",
    get_webhook_subscription,
    methods=["GET"],
    response_model=WebhookSubscriptionRead,
)


router.add_api_route(
    "/{subscription_id}",
    update_webhook_subscription,
    methods=["PATCH"],
    response_model=WebhookSubscriptionRead,
)


router.add_api_route(
    "/{subscription_id}",
    deactivate_webhook_subscription,
    methods=["DELETE"],
    response_model=None,
    status_code=status.HTTP_204_NO_CONTENT,
)


@router.get("", response_model=WebhookSubscriptionPage)
async def list_webhooks(
    service: WebhookSubscriptionServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WebhookSubscriptionPage:
    items, total = await service.list_page(offset=offset, limit=limit)
    return WebhookSubscriptionPage(
        items=[WebhookSubscriptionRead.model_validate(item) for item in items],
        total=total,
    )


@router.get("/{subscription_id}/deliveries", response_model=WebhookDeliveryPage)
async def list_subscription_deliveries(
    subscription_id: Annotated[int, Path(gt=0)],
    service: WebhookDeliveryHistoryServiceDep,
    offset: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> WebhookDeliveryPage:
    items, total = await service.list_subscription_deliveries(
        subscription_id, offset=offset, limit=limit
    )
    return WebhookDeliveryPage(
        items=[WebhookDeliveryListItem.model_validate(item) for item in items],
        total=total,
    )
