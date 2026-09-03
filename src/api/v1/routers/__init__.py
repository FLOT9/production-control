from fastapi import APIRouter

from src.api.v1.routers.batches import router as batches_router
from src.api.v1.routers.work_centers import router as work_centers_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(work_centers_router)
api_v1_router.include_router(batches_router)

__all__ = ("api_v1_router",)
