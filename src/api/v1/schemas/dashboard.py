from pydantic import BaseModel, ConfigDict, Field


class DashboardSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_batches: int = Field(ge=0)
    open_batches: int = Field(ge=0)
    closed_batches: int = Field(ge=0)
    total_products: int = Field(ge=0)
    aggregated_products: int = Field(ge=0)
    pending_products: int = Field(ge=0)
    aggregation_percent: float = Field(ge=0, le=100)
