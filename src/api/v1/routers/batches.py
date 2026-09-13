from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import RedirectResponse
from starlette.concurrency import run_in_threadpool

from src.api.dependencies.batches import BatchServiceDep
from src.api.v1.schemas import (
    BatchCreate,
    BatchListResponse,
    BatchRead,
    BatchUpdate,
    ReportGenerationTaskRead,
    ReportGenerationTaskStatusRead,
)
from src.application.services.report_download_service import ReportDownloadService
from src.core.dependencies import get_report_download_service
from src.tasks.batch_tasks import export_batches_csv as export_batches_csv_task
from src.tasks.task_status import get_task_status

router = APIRouter(
    prefix="/batches",
    tags=["batches"],
)


@router.post(
    "",
    response_model=BatchRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_batch(
    payload: BatchCreate,
    service: BatchServiceDep,
) -> BatchRead:
    batch = await service.create(**payload.model_dump())
    return BatchRead.model_validate(batch)


@router.post(
    "/export/csv",
    response_model=ReportGenerationTaskRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def export_batches_csv(
    is_closed: bool | None = None,
    batch_number: int | None = Query(None, gt=0),
    batch_date: date | None = None,
    work_center_id: int | None = Query(None, gt=0),
    shift: str | None = Query(None, min_length=1, max_length=50),
) -> ReportGenerationTaskRead:
    task = await run_in_threadpool(
        export_batches_csv_task.delay,
        is_closed=is_closed,
        batch_number=batch_number,
        batch_date=batch_date.isoformat() if batch_date else None,
        work_center_id=work_center_id,
        shift=shift,
    )
    return ReportGenerationTaskRead(task_id=task.id)


@router.get(
    "/export/tasks/{task_id}",
    response_model=ReportGenerationTaskStatusRead,
)
async def batch_export_task_status(task_id: str) -> ReportGenerationTaskStatusRead:
    task_data = await run_in_threadpool(get_task_status, task_id)
    return ReportGenerationTaskStatusRead(**task_data)


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
    "/{batch_id}",
    response_model=BatchRead,
)
async def get_batch(
    batch_id: int,
    service: BatchServiceDep,
) -> BatchRead:
    batch = await service.get_by_id(batch_id)
    return BatchRead.model_validate(batch)


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
    is_closed: bool | None = None,
    batch_number: int | None = Query(None, gt=0),
    batch_date: date | None = None,
    work_center_id: int | None = Query(None, gt=0),
    shift: str | None = Query(None, min_length=1, max_length=50),
    offset: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
) -> BatchListResponse:
    batches, total = await service.list_batches(
        is_closed=is_closed,
        batch_number=batch_number,
        batch_date=batch_date,
        work_center_id=work_center_id,
        shift=shift,
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
