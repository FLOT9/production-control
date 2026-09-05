from typing import Annotated

from fastapi import APIRouter, Depends
from starlette import status

from src.api.v1.schemas import ProductCreate, ProductRead
from src.core.dependencies import get_product_service
from src.domain.services.product_service import ProductService

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
    product = ProductRead.model_validate(product)
    return product


@router.patch(
    "/{unique_code}/aggregate",
    response_model=ProductRead,
)
async def aggregate_product(
    service: ProductServiceDep,
    unique_code: str,
) -> ProductRead:
    product = await service.aggregate(unique_code=unique_code)
    product = ProductRead.model_validate(product)

    return product
