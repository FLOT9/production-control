from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WorkCenterBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    identifier: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=255)


class WorkCenterCreate(WorkCenterBase):
    pass


class WorkCenterRead(WorkCenterBase):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    id: int
    created_at: datetime
    updated_at: datetime