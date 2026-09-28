from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BatchFilters:
    is_closed: bool | None = None
    batch_number: int | None = None
    batch_date: date | None = None
    work_center_id: int | None = None
    shift: str | None = None
