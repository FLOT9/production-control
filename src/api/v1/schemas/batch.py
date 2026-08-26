from datetime import date, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


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
    shift_start: datetime
    shift_end: datetime

    @model_validator(mode="after")
    def validate_shift_period(self) -> Self:
        if self.shift_end <= self.shift_start:
            raise ValueError("shift_end must be later than shift_start")
        return self


class BatchCreate(BatchBase):
    pass


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
