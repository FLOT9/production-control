from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FoundBatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(strict=True, gt=0, le=2**31 - 1)
    batch_number: int = Field(strict=True, gt=0, le=2**31 - 1)
    batch_date: date
    work_center_id: int = Field(strict=True, gt=0, le=2**31 - 1)
    is_closed: bool = Field(strict=True)


class BatchSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FoundBatch] = Field(max_length=10)
    total: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def check_page(self) -> "BatchSearchResult":
        if self.total < len(self.items) or (self.total > 0 and not self.items):
            raise ValueError("Список партий не соответствует общему количеству")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("В списке повторяются ID партий")
        return self


class BatchStatisticsResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    total: int = Field(ge=0)
    aggregated: int = Field(ge=0)
    remaining: int = Field(ge=0)

    @model_validator(mode="after")
    def check_counts(self) -> "BatchStatisticsResult":
        if self.aggregated + self.remaining != self.total:
            raise ValueError("Показатели партии не согласованы")
        return self


class AssistantData(BatchStatisticsResult):
    batch_id: int = Field(gt=0, le=2**31 - 1)


class AssistantResult(BaseModel):
    status: Literal["answered", "not_found", "insufficient_data", "needs_clarification"]
    answer: str
    data: AssistantData | None = None
    search: BatchSearchResult | None = None
    tools_called: list[str] = Field(default_factory=list)
