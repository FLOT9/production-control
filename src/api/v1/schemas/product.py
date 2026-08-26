from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


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
