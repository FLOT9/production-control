from dataclasses import dataclass
from datetime import date, datetime


@dataclass(frozen=True, slots=True)
class BatchIntegrationData:
    is_closed: bool
    task_description: str
    work_center_name: str
    work_center_identifier: str
    shift: str
    team: str
    batch_number: int
    batch_date: date
    nomenclature: str
    ekn_code: str
    shift_start: datetime
    shift_end: datetime
