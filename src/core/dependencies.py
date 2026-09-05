from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.data.unit_of_work import UnitOfWork
from src.domain.services.batch_service import BatchService
from src.domain.services.product_service import ProductService
from src.domain.services.work_center_service import WorkCenterService


async def get_uow(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UnitOfWork:
    return UnitOfWork(session)


async def get_work_center_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> WorkCenterService:
    return WorkCenterService(uow)


async def get_batch_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchService:
    return BatchService(uow)


async def get_product_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> ProductService:
    return ProductService(uow)
