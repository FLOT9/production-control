from typing import Annotated

from fastapi import Depends

from src.application.dto.analytics import BatchAnalyticsSnapshot, DashboardAnalytics
from src.application.services.analytics_dashboard_service import (
    AnalyticsDashboardService,
)
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_comparison_service import BatchComparisonService
from src.core.config import settings
from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork
from src.storage.analytics_cache import AnalyticsCache
from src.storage.redis import redis_client


def get_analytics_dashboard_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> AnalyticsDashboardService:
    return AnalyticsDashboardService(
        uow,
        AnalyticsCache(
            redis_client, DashboardAnalytics, settings.dashboard_cache_ttl_seconds
        ),
    )


def get_batch_analytics_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchAnalyticsService:
    return BatchAnalyticsService(
        uow,
        AnalyticsCache(
            redis_client,
            BatchAnalyticsSnapshot,
            settings.batch_statistics_cache_ttl_seconds,
        ),
    )


def get_batch_comparison_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchComparisonService:
    return BatchComparisonService(uow)


AnalyticsDashboardServiceDep = Annotated[
    AnalyticsDashboardService, Depends(get_analytics_dashboard_service)
]
BatchAnalyticsServiceDep = Annotated[
    BatchAnalyticsService, Depends(get_batch_analytics_service)
]
BatchComparisonServiceDep = Annotated[
    BatchComparisonService, Depends(get_batch_comparison_service)
]
