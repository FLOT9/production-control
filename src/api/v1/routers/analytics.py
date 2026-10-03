from datetime import date
from typing import Annotated

from fastapi import APIRouter, HTTPException, Query

from src.api.dependencies.analytics import (
    AnalyticsDashboardServiceDep,
    BatchComparisonServiceDep,
)
from src.api.v1.schemas.analytics import (
    BatchComparisonRead,
    BatchComparisonRequest,
    DashboardAnalyticsRead,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/dashboard", response_model=DashboardAnalyticsRead)
async def get_dashboard(
    service: AnalyticsDashboardServiceDep,
    date_from: date | None = None,
    date_to: date | None = None,
    work_center_id: Annotated[int | None, Query(gt=0, le=2**31 - 1)] = None,
    shift: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
) -> DashboardAnalyticsRead:
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(
            status_code=422, detail="date_from must not be after date_to"
        )
    result = await service.get_dashboard(
        date_from=date_from, date_to=date_to, work_center_id=work_center_id, shift=shift
    )
    return DashboardAnalyticsRead.model_validate(result)


@router.post("/compare-batches", response_model=BatchComparisonRead)
async def compare_batches(
    payload: BatchComparisonRequest, service: BatchComparisonServiceDep
) -> BatchComparisonRead:
    return BatchComparisonRead.model_validate(await service.compare(payload.batch_ids))
