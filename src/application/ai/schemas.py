"""Validated arguments for production assistant tools."""

from datetime import date
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BatchStatisticsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: int = Field(gt=0, le=2**31 - 1)


class DashboardArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date
    date_to: date

    @model_validator(mode="after")
    def validate_date_range(self) -> Self:
        if self.date_from > self.date_to:
            raise ValueError("date_from must not be after date_to")
        return self


class FindBatchesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: int = Field(strict=True, ge=1, le=2**31 - 1)
    batch_date: date | None = None
    limit: int = Field(default=5, strict=True, ge=1, le=10)
    include_statistics: bool = Field(
        default=False,
        strict=True,
        description=(
            "Укажи true, если спрашивают показатели партии по её номеру. "
            "Для обычного поиска оставь false."
        ),
    )
