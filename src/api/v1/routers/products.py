from typing import Annotated

from fastapi import APIRouter, Depends
from starlette import status
from starlette.concurrency import run_in_threadpool

from src.api.v1.schemas import (
    ProductAggregationRequest,
    ProductAggregationTaskRead,
    ProductAggregationTaskStatusRead,
    ProductCreate,
    ProductRead,
)
from src.application.services.product_service import ProductService
from src.core.dependencies import get_product_service
from src.tasks.product_tasks import (
    aggregate_products as aggregate_products_task,
)
from src.tasks.task_status import get_task_status

router = APIRouter(
    prefix="/products",
    tags=["products"],
)

ProductServiceDep = Annotated[
    ProductService,
    Depends(get_product_service),
]


@router.post(
    "",
    response_model=ProductRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_product(
    payload: ProductCreate,
    service: ProductServiceDep,
) -> ProductRead:
    product = await service.create(**payload.model_dump())
    return ProductRead.model_validate(product)


@router.patch(
    "/{unique_code}/aggregate",
    response_model=ProductRead,
)
async def aggregate_product(
    service: ProductServiceDep,
    unique_code: str,
) -> ProductRead:
    product = await service.aggregate(unique_code=unique_code)
    return ProductRead.model_validate(product)


@router.post(
    "/aggregate-bulk",
    response_model=ProductAggregationTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def aggregate_products_bulk(
    payload: ProductAggregationRequest,
) -> ProductAggregationTaskRead:
    task = await run_in_threadpool(
        aggregate_products_task.delay,
        payload.unique_codes,
    )

    return ProductAggregationTaskRead(task_id=task.id)


@router.get(
    "/tasks/{task_id}",
    response_model=ProductAggregationTaskStatusRead,
)
async def aggregate_task_status(
    task_id: str,
) -> ProductAggregationTaskStatusRead:
    task_data = await run_in_threadpool(get_task_status, task_id)
    return ProductAggregationTaskStatusRead.model_validate(task_data)
