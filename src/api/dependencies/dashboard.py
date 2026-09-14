from typing import Annotated

from fastapi import Depends

from src.application.services.dashboard_service import DashboardService
from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork


async def get_dashboard_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> DashboardService:
    return DashboardService(uow)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
