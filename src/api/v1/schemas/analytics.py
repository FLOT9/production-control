from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.v1.schemas.common import PositiveInt32
from src.application.dto.analytics import (
    BatchAnalytics,
    BatchComparison,
    DashboardAnalytics,
)


class BatchComparisonRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_ids: list[PositiveInt32] = Field(min_length=2, max_length=10)

    @model_validator(mode="after")
    def unique_ids(self) -> Self:
        if len(self.batch_ids) != len(set(self.batch_ids)):
            raise ValueError("batch_ids must be unique")
        return self


class DashboardAnalyticsRead(DashboardAnalytics):
    pass


class BatchAnalyticsRead(BatchAnalytics):
    pass


class BatchComparisonRead(BatchComparison):
    pass
