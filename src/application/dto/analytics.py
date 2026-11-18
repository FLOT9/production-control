from datetime import date, datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.dto.common import PositiveInt32


class AnalyticsModel(BaseModel):
    model_config = ConfigDict(frozen=True, from_attributes=True)


class ProductMetrics(AnalyticsModel):
    total_products: int = Field(ge=0)
    aggregated_products: int = Field(ge=0)
    pending_products: int = Field(ge=0)
    aggregation_percent: float = Field(ge=0, le=100)


class DashboardMetrics(ProductMetrics):
    total_batches: int = Field(ge=0)
    open_batches: int = Field(ge=0)
    closed_batches: int = Field(ge=0)


class ShiftMetrics(DashboardMetrics):
    shift: str


class WorkCenterMetrics(DashboardMetrics):
    work_center_id: int
    name: str


class DashboardAnalytics(AnalyticsModel):
    summary: DashboardMetrics
    today: DashboardMetrics
    by_shift: list[ShiftMetrics]
    top_work_centers: list[WorkCenterMetrics]
    cached_at: datetime | None = None


class BatchInfo(AnalyticsModel):
    id: int
    batch_number: int
    batch_date: date
    nomenclature: str
    work_center_id: int
    work_center_name: str
    shift: str
    team: str
    is_closed: bool
    shift_start: datetime
    shift_end: datetime
    closed_at: datetime | None


class BatchAnalyticsSnapshot(AnalyticsModel):
    batch_info: BatchInfo
    total_products: int
    aggregated_products: int
    window_products: int
    last_aggregated_at: datetime | None
    observed_at: datetime
    cached_at: datetime | None = None


ForecastStatus = Literal[
    "no_products",
    "not_started",
    "completed",
    "batch_closed",
    "shift_finished",
    "no_progress",
    "available",
]


class BatchTimeline(AnalyticsModel):
    duration_hours: float
    elapsed_hours: float
    products_per_hour: float | None
    estimated_completion_at: datetime | None
    forecast_status: ForecastStatus


class TeamPerformance(ProductMetrics):
    team: str
    products_per_hour: float | None


class BatchAnalytics(ProductMetrics):
    batch_id: int
    batch_info: BatchInfo
    timeline: BatchTimeline
    team_performance: TeamPerformance
    cached_at: datetime | None


class BatchComparisonItem(ProductMetrics):
    batch_info: BatchInfo
    duration_hours: float
    products_per_hour: float


class ComparisonAverage(AnalyticsModel):
    duration_hours: float
    total_products: float
    aggregated_products: float
    pending_products: float
    aggregation_percent: float
    products_per_hour: float


class BatchComparison(AnalyticsModel):
    items: list[BatchComparisonItem]
    average: ComparisonAverage
    overall_products_per_hour: float


class BatchComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_ids: list[PositiveInt32] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(self.batch_ids) != len(set(self.batch_ids)):
            raise ValueError("batch_ids must be unique")
        return self
