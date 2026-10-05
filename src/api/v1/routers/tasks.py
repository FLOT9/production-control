from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool

from src.api.v1.schemas.task import TaskStatusRead
from src.tasks.task_status import get_task_status

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("/{task_id}", response_model=TaskStatusRead)
async def task_status(task_id: str) -> TaskStatusRead:
    task_data = await run_in_threadpool(get_task_status, task_id)
    return TaskStatusRead.model_validate(task_data)
