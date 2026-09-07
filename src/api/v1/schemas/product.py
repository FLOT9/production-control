from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)


class ProductAggregationTaskRead(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"


class ProductBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    unique_code: str = Field(min_length=1, max_length=255)
    batch_id: int = Field(gt=0)


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    model_config = ConfigDict(
        from_attributes=True,
        str_strip_whitespace=True,
    )

    id: int
    is_aggregated: bool
    aggregated_at: datetime | None
    created_at: datetime


ProductCode = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=255,
    ),
]


class ProductAggregationRequest(BaseModel):
    unique_codes: list[ProductCode] = Field(min_length=1)

    @field_validator("unique_codes")
    @classmethod
    def validate_unique_codes(cls, codes: list[str]) -> list[str]:
        if len(codes) != len(set(codes)):
            raise ValueError("unique_codes must not contain duplicates")

        return codes
