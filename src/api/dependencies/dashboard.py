from typing import Annotated

from fastapi import Depends

from src.application.services.dashboard_service import DashboardService
from src.core.dependencies import get_dashboard_cache, get_uow
from src.data.unit_of_work import UnitOfWork
from src.storage.dashboard_cache import DashboardCache


async def get_dashboard_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
    cache: Annotated[DashboardCache, Depends(get_dashboard_cache)],
) -> DashboardService:
    return DashboardService(uow, cache)


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
