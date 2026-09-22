from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4


class WebhookEventType(StrEnum):
    BATCH_CREATED = "batch_created"
    BATCH_UPDATED = "batch_updated"
    BATCH_CLOSED = "batch_closed"
    BATCH_REOPENED = "batch_reopened"
    PRODUCT_CREATED = "product_created"
    PRODUCT_AGGREGATED = "product_aggregated"


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    event_type: WebhookEventType
    data: dict[str, Any]
    event_id: UUID = field(default_factory=uuid4)
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))
