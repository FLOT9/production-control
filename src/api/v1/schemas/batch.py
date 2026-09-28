from datetime import date, datetime
from typing import Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from src.application.dto.batch_import import BatchImportResult


class BatchBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    task_description: str = Field(min_length=1)
    work_center_id: int = Field(gt=0)
    shift: str = Field(min_length=1, max_length=50)
    team: str = Field(min_length=1, max_length=255)
    batch_number: int = Field(gt=0)
    batch_date: date
    nomenclature: str = Field(min_length=1, max_length=255)
    ekn_code: str = Field(min_length=1, max_length=100)
    shift_start: AwareDatetime
    shift_end: AwareDatetime

    @model_validator(mode="after")
    def validate_shift_period(self) -> Self:
        if self.shift_end <= self.shift_start:
            raise ValueError("shift_end must be later than shift_start")
        return self


class BatchCreate(BatchBase):
    pass


class BatchUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    task_description: str | None = Field(default=None, min_length=1)
    work_center_id: int | None = Field(default=None, gt=0)
    shift: str | None = Field(default=None, min_length=1, max_length=50)
    team: str | None = Field(default=None, min_length=1, max_length=255)
    batch_number: int | None = Field(default=None, gt=0)
    batch_date: date | None = None
    nomenclature: str | None = Field(default=None, min_length=1, max_length=255)
    ekn_code: str | None = Field(default=None, min_length=1, max_length=100)
    shift_start: AwareDatetime | None = None
    shift_end: AwareDatetime | None = None
    is_closed: bool | None = None

    @model_validator(mode="after")
    def validate_shift_period(self) -> Self:
        if any(
            getattr(self, field_name) is None for field_name in self.model_fields_set
        ):
            raise ValueError("update fields cannot be null")

        if (
            self.shift_start is not None
            and self.shift_end is not None
            and self.shift_end <= self.shift_start
        ):
            raise ValueError("shift_end must be later than shift_start")

        return self


class BatchRead(BatchBase):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    id: int
    is_closed: bool
    closed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class BatchListResponse(BaseModel):
    items: list[BatchRead]
    total: int
    offset: int
    limit: int


class BatchStatisticsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    batch_id: int
    total_products: int = Field(ge=0)
    aggregated_products: int = Field(ge=0)
    pending_products: int = Field(ge=0)
    aggregation_percent: float = Field(ge=0, le=100)


class BatchComparisonRead(BaseModel):
    items: list[BatchStatisticsRead]


class BatchImportTaskStatusRead(BaseModel):
    task_id: str
    status: str
    result: BatchImportResult | None = None
    error: str | None = None
