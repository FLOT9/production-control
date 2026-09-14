from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from src.api.dependencies.dashboard import DashboardServiceDep
from src.api.v1.schemas.dashboard import DashboardSummaryRead

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummaryRead)
async def get_dashboard_summary(
    service: DashboardServiceDep,
    batch_date: date | None = None,
    work_center_id: Annotated[int | None, Query(gt=0)] = None,
    shift: Annotated[str | None, Query(min_length=1, max_length=50)] = None,
) -> DashboardSummaryRead:
    summary = await service.get_summary(
        batch_date=batch_date,
        work_center_id=work_center_id,
        shift=shift,
    )
    return DashboardSummaryRead.model_validate(summary)
