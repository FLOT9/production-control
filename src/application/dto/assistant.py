from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    status: Literal["answered", "not_found", "insufficient_data"]
    answer: str
    data: AssistantData | None = None
    tools_called: list[str] = Field(default_factory=list)
