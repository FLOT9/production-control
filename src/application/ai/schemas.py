"""Validated arguments for production assistant tools."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class BatchStatisticsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: int = Field(gt=0, le=2**31 - 1)


class FindBatchesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: int = Field(strict=True, ge=1, le=2**31 - 1)
    batch_date: date | None = None
    limit: int = Field(default=5, strict=True, ge=1, le=10)
