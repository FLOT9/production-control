from pydantic import BaseModel, ConfigDict, Field

from src.application.dto.assistant import AssistantResult


class AssistantAskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)


class AssistantAskResponse(AssistantResult):
    model_config = ConfigDict(from_attributes=True)
