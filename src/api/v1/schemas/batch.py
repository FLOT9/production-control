from datetime import UTC, date, datetime
from typing import Self
from zoneinfo import ZoneInfo

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from src.api.v1.schemas.common import PositiveInt32
from src.api.v1.schemas.product import ProductShort
from src.api.v1.schemas.task import TaskStatusRead
from src.core.config import settings


class BatchIntegrationItem(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    is_closed: bool = Field(alias="СтатусЗакрытия")
    task_description: str = Field(
        alias="ПредставлениеЗаданияНаСмену",
        min_length=1,
    )
    work_center_name: str = Field(alias="РабочийЦентр", min_length=1, max_length=255)
    work_center_identifier: str = Field(
        alias="ИдентификаторРЦ", min_length=1, max_length=100
    )
    shift: str = Field(alias="Смена", min_length=1, max_length=50)
    team: str = Field(alias="Бригада", min_length=1, max_length=255)
    batch_number: PositiveInt32 = Field(alias="НомерПартии")
    batch_date: date = Field(alias="ДатаПартии")
    nomenclature: str = Field(alias="Номенклатура", min_length=1, max_length=255)
    ekn_code: str = Field(alias="КодЕКН", min_length=1, max_length=100)
    shift_start: datetime = Field(alias="ДатаВремяНачалаСмены")
    shift_end: datetime = Field(alias="ДатаВремяОкончанияСмены")

    @field_validator("shift_start", "shift_end")
    @classmethod
    def normalize_shift_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            value = value.replace(tzinfo=ZoneInfo(settings.production_timezone))
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_shift_period(self) -> Self:
        if self.shift_end <= self.shift_start:
            raise ValueError("shift_end must be later than shift_start")
        return self


class BatchBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    task_description: str = Field(min_length=1)
    work_center_id: PositiveInt32
    shift: str = Field(min_length=1, max_length=50)
    team: str = Field(min_length=1, max_length=255)
    batch_number: PositiveInt32
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
    work_center_id: PositiveInt32 | None = None
    shift: str | None = Field(default=None, min_length=1, max_length=50)
    team: str | None = Field(default=None, min_length=1, max_length=255)
    batch_number: PositiveInt32 | None = None
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


class BatchDetailsRead(BatchRead):
    products: list[ProductShort]


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


class BatchImportTaskStatusRead(TaskStatusRead):
    pass
