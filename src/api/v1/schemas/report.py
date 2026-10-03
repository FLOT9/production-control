from typing import Literal

from pydantic import BaseModel

from src.api.v1.schemas.task import TaskStatusRead


class ReportGenerationTaskRead(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"


class ReportGenerationTaskStatusRead(TaskStatusRead):
    pass
