import uuid
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Body,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import RedirectResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from src.api.dependencies.batches import BatchFiltersDep, BatchServiceDep
from src.api.v1.schemas import (
    BatchComparisonRead,
    BatchDetailsRead,
    BatchImportTaskStatusRead,
    BatchIntegrationItem,
    BatchListResponse,
    BatchRead,
    BatchStatisticsRead,
    BatchUpdate,
    ProductAggregationRequest,
    ProductAggregationTaskRead,
    ReportGenerationTaskRead,
    ReportGenerationTaskStatusRead,
)
from src.application.dto import BatchIntegrationData
from src.application.services.product_service import (
    ProductAggregationResult,
    ProductService,
)
from src.application.services.report_download_service import ReportDownloadService
from src.core.config import settings
from src.core.dependencies import get_product_service, get_report_download_service
from src.storage.object_storage import create_object_storage
from src.tasks.batch_tasks import export_batches_csv as export_batches_csv_task
from src.tasks.batch_tasks import import_batches_csv as import_batches_csv_task
from src.tasks.product_tasks import aggregate_products as aggregate_products_task
from src.tasks.task_status import get_task_status

router = APIRouter(
    prefix="/batches",
    tags=["batches"],
)

ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]


@router.post("/{batch_id}/aggregate", response_model=dict[str, object])
async def aggregate_batch_products(
    batch_id: int,
    payload: ProductAggregationRequest,
    service: ProductServiceDep,
) -> ProductAggregationResult:
    return await service.aggregate_many(
        batch_id=batch_id,
        unique_codes=payload.unique_codes,
    )


@router.post(
    "/{batch_id}/aggregate-async",
    response_model=ProductAggregationTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def aggregate_batch_products_async(
    batch_id: int,
    payload: ProductAggregationRequest,
) -> ProductAggregationTaskRead:
    task = await run_in_threadpool(
        aggregate_products_task.delay,
        batch_id=batch_id,
        unique_codes=payload.unique_codes,
    )
    return ProductAggregationTaskRead(task_id=task.id)


@router.post(
    "",
    response_model=list[BatchRead],
    status_code=status.HTTP_201_CREATED,
)
async def create_batches(
    payload: Annotated[list[BatchIntegrationItem], Body(min_length=1, max_length=1000)],
    service: BatchServiceDep,
) -> list[BatchRead]:
    items = [BatchIntegrationData(**item.model_dump()) for item in payload]
    batches = await service.create_many(items)
    return [BatchRead.model_validate(batch) for batch in batches]


@router.post(
    "/export/csv",
    response_model=ReportGenerationTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_batches_csv(
    filters: BatchFiltersDep,
) -> ReportGenerationTaskRead:
    task = await run_in_threadpool(
        export_batches_csv_task.delay,
        is_closed=filters.is_closed,
        batch_number=filters.batch_number,
        batch_date=filters.batch_date.isoformat() if filters.batch_date else None,
        work_center_id=filters.work_center_id,
        shift=filters.shift,
    )
    return ReportGenerationTaskRead(task_id=task.id)


@router.get(
    "/export/tasks/{task_id}",
    response_model=ReportGenerationTaskStatusRead,
)
async def batch_export_task_status(task_id: str) -> ReportGenerationTaskStatusRead:
    task_data = await run_in_threadpool(get_task_status, task_id)
    return ReportGenerationTaskStatusRead.model_validate(task_data)


@router.get("/exports/{report_id}/download")
async def download_batch_export(
    report_id: UUID,
    service: Annotated[
        ReportDownloadService,
        Depends(get_report_download_service),
    ],
) -> RedirectResponse:
    url = await service.get_batch_export_url(report_id)
    return RedirectResponse(
        url=url,
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
    )


@router.get(
    "/compare",
    response_model=BatchComparisonRead,
)
async def compare_batches(
    batch_ids: Annotated[
        list[Annotated[int, Field(gt=0)]], Query(min_length=2, max_length=10)
    ],
    service: BatchServiceDep,
) -> BatchComparisonRead:
    statistics = await service.compare_batches(batch_ids)
    return BatchComparisonRead(
        items=[BatchStatisticsRead.model_validate(item) for item in statistics]
    )


@router.get(
    "/{batch_id}/statistics",
    response_model=BatchStatisticsRead,
)
async def get_batch_statistics(
    batch_id: int,
    service: BatchServiceDep,
) -> BatchStatisticsRead:
    statistics = await service.get_statistics(batch_id)
    return BatchStatisticsRead.model_validate(statistics)


@router.get(
    "/{batch_id}",
    response_model=BatchDetailsRead,
)
async def get_batch(
    batch_id: int,
    service: BatchServiceDep,
) -> BatchDetailsRead:
    batch = await service.get_by_id(batch_id)
    return BatchDetailsRead.model_validate(batch)


@router.patch(
    "/{batch_id}",
    response_model=BatchRead,
)
async def update_batch(
    batch_id: int,
    payload: BatchUpdate,
    service: BatchServiceDep,
) -> BatchRead:
    batch = await service.update(
        batch_id,
        payload.model_dump(exclude_unset=True),
    )
    return BatchRead.model_validate(batch)


@router.delete(
    "/{batch_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_batch(
    batch_id: int,
    service: BatchServiceDep,
) -> None:
    await service.delete(batch_id)


@router.get(
    "",
    response_model=BatchListResponse,
)
async def list_batches(
    service: BatchServiceDep,
    filters: BatchFiltersDep,
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> BatchListResponse:
    batches, total = await service.list_batches(
        filters=filters,
        offset=offset,
        limit=limit,
    )

    result = BatchListResponse(
        items=[BatchRead.model_validate(batch) for batch in batches],
        total=total,
        offset=offset,
        limit=limit,
    )
    return result


@router.post(
    "/import/csv",
    response_model=ReportGenerationTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def import_batches_csv(
    file: Annotated[UploadFile, File()],
) -> ReportGenerationTaskRead:
    data = await file.read(settings.batch_import_max_file_size_bytes + 1)
    if len(data) > settings.batch_import_max_file_size_bytes:
        raise HTTPException(status_code=413, detail="File too large")
    object_name = f"batch-imports/{uuid.uuid4().hex}.csv"
    storage = create_object_storage()

    await run_in_threadpool(
        storage.upload,
        "imports",
        object_name,
        data,
        "text/csv",
    )

    task = await run_in_threadpool(import_batches_csv_task.delay, object_name)
    return ReportGenerationTaskRead(task_id=task.id)


@router.get(
    "/import/tasks/{task_id}",
    response_model=BatchImportTaskStatusRead,
)
async def batch_import_task_status(task_id: str) -> BatchImportTaskStatusRead:
    task_data = await run_in_threadpool(get_task_status, task_id)
    return BatchImportTaskStatusRead.model_validate(task_data)
