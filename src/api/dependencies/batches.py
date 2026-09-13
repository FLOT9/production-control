from typing import Annotated

from fastapi import Depends

from src.core.dependencies import get_uow
from src.data.unit_of_work import UnitOfWork
from src.domain.services.batch_service import BatchService


async def get_batch_service(
    uow: Annotated[UnitOfWork, Depends(get_uow)],
) -> BatchService:
    return BatchService(uow)


BatchServiceDep = Annotated[
    BatchService,
    Depends(get_batch_service),
]
