from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.application.services.report_download_service import ReportDownloadService
from src.core.database import get_db
from src.data.unit_of_work import UnitOfWork
from src.domain.services.product_service import ProductService
from src.storage.object_storage import create_object_storage


async def get_uow(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UnitOfWork:
    return UnitOfWork(session)


async def get_product_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> ProductService:
    return ProductService(uow)


async def get_report_download_service() -> ReportDownloadService:
    return ReportDownloadService(create_object_storage())
