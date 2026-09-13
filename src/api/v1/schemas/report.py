from typing import Literal

from pydantic import BaseModel


class ReportGenerationTaskRead(BaseModel):
    task_id: str
    status: Literal["queued"] = "queued"


class ReportGenerationTaskStatusRead(BaseModel):
    task_id: str
    status: str
    result: dict[str, str] | None = None
