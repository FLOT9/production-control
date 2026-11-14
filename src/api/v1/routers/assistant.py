from fastapi import APIRouter

from src.api.dependencies.assistant import AssistantServiceDep
from src.api.v1.schemas.assistant import AssistantAskRequest, AssistantAskResponse

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post("/ask", response_model=AssistantAskResponse)
async def ask_assistant(
    payload: AssistantAskRequest,
    service: AssistantServiceDep,
) -> AssistantAskResponse:
    result = await service.ask(payload.question)
    return AssistantAskResponse.model_validate(result)
