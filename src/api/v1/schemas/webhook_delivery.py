from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class WebhookDeliveryAttemptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    attempt_number: int
    attempted_at: datetime
    response_status: int | None
    duration_ms: int | None
    response_body: str | None
    error_message: str | None


class WebhookDeliveryListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: UUID
    subscription_id: int
    event_type: str
    target_url: str
    status: str
    attempts: int
    response_status: int | None
    error_message: str | None
    next_attempt_at: datetime | None
    created_at: datetime
    delivered_at: datetime | None


class WebhookDeliveryDetails(WebhookDeliveryListItem):
    payload: dict[str, Any]
    response_body: str | None
    attempt_history: list[WebhookDeliveryAttemptRead]
