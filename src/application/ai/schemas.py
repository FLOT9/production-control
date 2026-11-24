"""Validated arguments for production assistant tools."""

from datetime import date
from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, WithJsonSchema, model_validator


class BatchStatisticsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: int = Field(gt=0, le=2**31 - 1)


AggregationDay = (
    Annotated[date, Field(gt=date.min, lt=date.max)] | Literal["today", "yesterday"]
)
OptionalDate = Annotated[
    date | None, WithJsonSchema({"type": "string", "format": "date"})
]
AggregationBoundary = Annotated[date, Field(gt=date.min, lt=date.max)]
OptionalAggregationBoundary = Annotated[
    AggregationBoundary | None, WithJsonSchema({"type": "string", "format": "date"})
]
OptionalWorkCenterId = Annotated[
    int | None,
    WithJsonSchema({"type": "integer", "description": "Внутренний ID цеха."}),
]
OptionalShift = Annotated[str | None, WithJsonSchema({"type": "string"})]


class AggregationDayArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    day: Annotated[
        AggregationDay | None,
        WithJsonSchema(
            {
                "type": "string",
                "description": "Дата в формате ГГГГ-ММ-ДД, today или yesterday.",
            }
        ),
    ] = None
    date_from: OptionalAggregationBoundary = None
    date_to: OptionalAggregationBoundary = None
    period: Annotated[
        Literal["last_week"] | None,
        WithJsonSchema({"type": "string", "enum": ["last_week"]}),
    ] = None
    work_center_id: OptionalWorkCenterId = Field(
        default=None, strict=True, gt=0, le=2**31 - 1
    )

    @model_validator(mode="after")
    def validate_period(self) -> Self:
        has_range = self.date_from is not None or self.date_to is not None
        if sum((self.day is not None, self.period is not None, has_range)) != 1:
            raise ValueError("Use day, a date range or last_week")
        if has_range and (
            self.date_from is None
            or self.date_to is None
            or self.date_from > self.date_to
        ):
            raise ValueError("Provide an ordered date range")
        return self


class DashboardArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date
    work_center_id: OptionalWorkCenterId = Field(
        default=None, strict=True, gt=0, le=2**31 - 1
    )
    shift: OptionalShift = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class FindBatchesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: Annotated[int | None, WithJsonSchema({"type": "integer"})] = Field(
        default=None, strict=True, ge=1, le=2**31 - 1
    )
    batch_date: OptionalDate = None
    date_from: OptionalDate = None
    date_to: OptionalDate = None
    work_center_id: OptionalWorkCenterId = Field(
        default=None, strict=True, gt=0, le=2**31 - 1
    )
    shift: OptionalShift = Field(default=None, min_length=1, max_length=50)
    is_closed: Annotated[bool | None, WithJsonSchema({"type": "boolean"})] = Field(
        default=None, strict=True
    )
    count_only: bool = Field(default=False, strict=True)
    limit: int = Field(default=5, strict=True, ge=1, le=10)
    include_statistics: bool = Field(
        default=False,
        strict=True,
        description=(
            "Укажи true, если спрашивают показатели партии по её номеру. "
            "Для обычного поиска оставь false."
        ),
    )

    @model_validator(mode="after")
    def validate_filters(self) -> Self:
        if self.batch_date is not None and (
            self.date_from is not None or self.date_to is not None
        ):
            raise ValueError("Use batch_date or a date range")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from must not be after date_to")
        if self.include_statistics and (self.batch_number is None or self.count_only):
            raise ValueError("Statistics require a batch number and a search")
        return self
