from dataclasses import dataclass
from datetime import date, datetime

from src.application.dto.batch_statistics import BatchStatistics


@dataclass(frozen=True, slots=True)
class BatchReportInfo:
    id: int
    task_description: str
    work_center_id: int
    shift: str
    team: str
    batch_number: int
    batch_date: date
    nomenclature: str
    ekn_code: str
    shift_start: datetime
    shift_end: datetime
    is_closed: bool
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class BatchReportProduct:
    id: int
    unique_code: str
    is_aggregated: bool
    aggregated_at: datetime | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class BatchReportData:
    batch: BatchReportInfo
    products: tuple[BatchReportProduct, ...]
    statistics: BatchStatistics
    generated_at: datetime
