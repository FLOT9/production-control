import asyncio

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ValidationError

from src.application.ai.exceptions import (
    AssistantTimeoutError,
    InvalidModelResponseError,
    InvalidToolResultError,
)
from src.application.ai.ports import AssistantModel
from src.application.dto.assistant import (
    AssistantData,
    AssistantResult,
    BatchStatisticsResult,
)
from src.domain.exceptions.batch import BatchNotFoundError


class AssistantService:
    def __init__(
        self,
        model: AssistantModel,
        statistics_tool: BaseTool,
        *,
        timeout_seconds: float = 15,
    ) -> None:
        self.tool = statistics_tool
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def ask(self, question: str) -> AssistantResult:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._ask(question)
        except TimeoutError as error:
            raise AssistantTimeoutError() from error

    async def _ask(self, question: str) -> AssistantResult:
        messages: list[BaseMessage] = [
            SystemMessage(
                content=(
                    "Ты ассистент производства. "
                    "Для получения показателей партии используй доступный инструмент. "
                    "Аргумент batch_id — внутренний ID, а не номер партии. "
                    "Если ID не указан, запроси уточнение. Не выдумывай показатели."
                )
            ),
            HumanMessage(content=question),
        ]
        response = await self.model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            raise InvalidModelResponseError()
        if not response.tool_calls:
            return AssistantResult(
                status="insufficient_data",
                answer="Недостаточно данных. Укажите ID партии для получения статистики.",
            )
        if len(response.tool_calls) != 1:
            raise InvalidModelResponseError()

        tool_call = response.tool_calls[0]
        if tool_call["name"] != self.tool.name:
            raise InvalidModelResponseError()
        batch_id = tool_call["args"].get("batch_id")
        if type(batch_id) is not int or not 0 < batch_id <= 2**31 - 1:
            raise InvalidModelResponseError()
        schema = self.tool.get_input_schema()
        if not issubclass(schema, BaseModel):
            raise TypeError("Инструмент должен использовать схему Pydantic v2")
        try:
            schema.model_validate(tool_call["args"])
        except ValidationError as error:
            raise InvalidModelResponseError() from error
        try:
            result = await self.tool.ainvoke(tool_call["args"])
        except BatchNotFoundError:
            return AssistantResult(
                status="not_found",
                answer="Партия не найдена.",
                tools_called=[self.tool.name],
            )
        try:
            statistics = BatchStatisticsResult.model_validate(result)
        except ValidationError as error:
            raise InvalidToolResultError() from error
        return AssistantResult(
            status="answered",
            answer=(
                f"Партия с ID {batch_id}: всего {statistics.total} изделий, "
                f"агрегировано {statistics.aggregated}, осталось {statistics.remaining}."
            ),
            data=AssistantData(batch_id=batch_id, **statistics.model_dump()),
            tools_called=[self.tool.name],
        )
