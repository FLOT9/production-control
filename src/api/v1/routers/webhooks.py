from fastapi import APIRouter, status

from src.api.dependencies.webhooks import WebhookSubscriptionServiceDep
from src.api.v1.schemas import (
    WebhookSubscriptionCreate,
    WebhookSubscriptionRead,
    WebhookSubscriptionUpdate,
)

router = APIRouter(
    prefix="/webhook-subscriptions",
    tags=["webhook-subscriptions"],
)


@router.post(
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


@router.get(
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


@router.get(
    "/{subscription_id}",
    response_model=WebhookSubscriptionRead,
)
async def get_webhook_subscription(
    subscription_id: int,
    service: WebhookSubscriptionServiceDep,
) -> WebhookSubscriptionRead:
    subscription = await service.get_by_id(subscription_id)
    return WebhookSubscriptionRead.model_validate(subscription)


@router.patch(
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


@router.delete(
    "/{subscription_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def deactivate_webhook_subscription(
    subscription_id: int,
    service: WebhookSubscriptionServiceDep,
) -> None:
    await service.deactivate(subscription_id)
