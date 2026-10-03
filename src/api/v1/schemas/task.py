from pydantic import BaseModel, Field


class TaskProgressRead(BaseModel):
    current: int = Field(ge=0)
    total: int = Field(ge=0)
    progress: int = Field(ge=0, le=100)


class TaskStatusRead(BaseModel):
    task_id: str
    status: str
    progress: TaskProgressRead | None = None
    result: dict[str, object] | None = None
    error: str | None = None
