from dataclasses import asdict
from datetime import date, datetime
from typing import Any

from src.application.dto.batch_statistics import BatchStatistics
from src.data.models import Batch


def json_value(value: object) -> object:
    return value.isoformat() if isinstance(value, date | datetime) else value


def build_batch_change_payload(
    batch: Batch,
    previous: dict[str, object],
    statistics: BatchStatistics | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "batch_id": batch.id,
        "batch_number": batch.batch_number,
        "batch_date": batch.batch_date.isoformat(),
        "work_center_id": batch.work_center_id,
        "shift": batch.shift,
        "is_closed": batch.is_closed,
        "changes": {
            name: {"old": json_value(old), "new": json_value(getattr(batch, name))}
            for name, old in previous.items()
            if old != getattr(batch, name)
        },
    }
    if statistics is not None:
        payload["statistics"] = asdict(statistics)
    return payload
