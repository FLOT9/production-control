from datetime import datetime
from typing import Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)

from src.application.events import WebhookEventType


class WebhookSubscriptionCreate(BaseModel):
    url: HttpUrl
    events: list[WebhookEventType] = Field(min_length=1)
    secret_key: str = Field(min_length=32, max_length=255)
    retry_count: int = Field(default=3, ge=0, le=10)
    timeout_seconds: int = Field(default=10, ge=1, le=60)


class WebhookSubscriptionUpdate(BaseModel):
    url: HttpUrl | None = None
    events: list[WebhookEventType] | None = Field(
        default=None,
        min_length=1,
    )
    secret_key: str | None = Field(
        default=None,
        min_length=32,
        max_length=255,
    )
    is_active: bool | None = None
    retry_count: int | None = Field(default=None, ge=0, le=10)
    timeout_seconds: int | None = Field(default=None, ge=1, le=60)

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> Self:
        if any(
            getattr(self, field_name) is None for field_name in self.model_fields_set
        ):
            raise ValueError("update fields cannot be null")

        return self


class WebhookSubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    url: HttpUrl
    events: list[WebhookEventType]
    is_active: bool
    retry_count: int
    timeout_seconds: int
    created_at: datetime
    updated_at: datetime


class WebhookSubscriptionPage(BaseModel):
    items: list[WebhookSubscriptionRead]
    total: int
