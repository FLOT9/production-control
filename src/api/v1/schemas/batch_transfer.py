from datetime import date
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.api.v1.schemas.common import PositiveInt32
from src.application.dto.batch_filters import BatchFilters

TransferFormat = Literal["csv", "excel"]


class BatchExportFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    is_closed: bool | None = None
    batch_number: PositiveInt32 | None = None
    batch_date: date | None = None
    work_center_id: PositiveInt32 | None = None
    shift: str | None = Field(default=None, min_length=1, max_length=50)
    date_from: date | None = None
    date_to: date | None = None

    @model_validator(mode="after")
    def check_dates(self) -> Self:
        BatchFilters(**self.model_dump())
        return self


class BatchExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: TransferFormat = "csv"
    filters: BatchExportFilters = Field(default_factory=BatchExportFilters)
