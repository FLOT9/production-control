from fastapi import APIRouter

from src.api.v1.routers.batches import router as batches_router
from src.api.v1.routers.dashboard import router as dashboard_router
from src.api.v1.routers.products import router as products_router
from src.api.v1.routers.reports import router as reports_router
from src.api.v1.routers.webhook_deliveries import router as webhook_deliveries_router
from src.api.v1.routers.webhooks import router as webhooks_router
from src.api.v1.routers.work_centers import router as work_centers_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(work_centers_router)
api_v1_router.include_router(batches_router)
api_v1_router.include_router(dashboard_router)

api_v1_router.include_router(products_router)
api_v1_router.include_router(reports_router)
api_v1_router.include_router(webhooks_router)
api_v1_router.include_router(webhook_deliveries_router)

__all__ = ("api_v1_router",)
