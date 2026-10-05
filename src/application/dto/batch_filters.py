from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class BatchFilters:
    is_closed: bool | None = None
    batch_number: int | None = None
    batch_date: date | None = None
    work_center_id: int | None = None
    shift: str | None = None
    date_from: date | None = None
    date_to: date | None = None

    def __post_init__(self) -> None:
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from must not be later than date_to")
        if self.batch_date and (self.date_from or self.date_to):
            raise ValueError("Use batch_date or a date range, not both")
