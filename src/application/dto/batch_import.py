from dataclasses import dataclass
from datetime import date
from typing import Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)


class BatchImportRow(BaseModel):
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


@dataclass(frozen=True, slots=True)
class BatchImportRowError:
    row_number: int
    reason: str


@dataclass(frozen=True, slots=True)
class ParsedBatchImportRow:
    row_number: int
    data: BatchImportRow


@dataclass(frozen=True, slots=True)
class BatchCsvParseResult:
    valid_rows: list[ParsedBatchImportRow]
    errors: list[BatchImportRowError]


@dataclass(frozen=True, slots=True)
class BatchImportProcessedRow:
    row_number: int
    batch_id: int


@dataclass(frozen=True, slots=True)
class BatchImportResult:
    processed: list[BatchImportProcessedRow]
    failed: list[BatchImportRowError]
