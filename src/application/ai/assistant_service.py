import asyncio

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from src.application.ai.exceptions import (
    AssistantTimeoutError,
    InvalidModelResponseError,
    InvalidToolResultError,
)
from src.application.ai.ports import AssistantModel
from src.application.ai.schemas import BatchStatisticsArgs, FindBatchesArgs
from src.application.dto.assistant import (
    AssistantData,
    AssistantResult,
    BatchSearchResult,
    BatchStatisticsResult,
)
from src.domain.exceptions.batch import BatchNotFoundError


class AssistantService:
    def __init__(
        self,
        model: AssistantModel,
        tools: list[BaseTool],
        *,
        timeout_seconds: float = 15,
    ) -> None:
        self.tools = {tool.name: tool for tool in tools}
        if not self.tools or len(self.tools) != len(tools):
            raise ValueError("Нужны инструменты с уникальными именами")
        if self.tools.keys() - {"get_batch_statistics", "find_batches"}:
            raise ValueError("Не поддерживается обработка результата инструмента")
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
                    "Для показателей по внутреннему ID вызывай get_batch_statistics. "
                    "Для поиска по производственному номеру и дате вызывай find_batches. "
                    "Номер партии не равен ID: не подставляй номер в batch_id. "
                    "Если найдено несколько партий, необходимо уточнить дату. "
                    "Каждый вопрос самостоятельный. Не выдумывай показатели."
                )
            ),
            HumanMessage(content=question),
        ]
        response = await self.model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            raise InvalidModelResponseError()
        if response.invalid_tool_calls:
            raise InvalidModelResponseError()
        if not response.tool_calls:
            return AssistantResult(
                status="insufficient_data",
                answer="Недостаточно данных. Укажите ID партии или её номер и дату для поиска.",
            )
        if len(response.tool_calls) != 1:
            raise InvalidModelResponseError()

        tool_call = response.tool_calls[0]
        selected_tool = self.tools.get(tool_call["name"])
        if selected_tool is None:
            raise InvalidModelResponseError()
        schema = (
            BatchStatisticsArgs
            if selected_tool.name == "get_batch_statistics"
            else FindBatchesArgs
        )
        try:
            arguments = schema.model_validate(tool_call["args"]).model_dump()
        except ValidationError as error:
            raise InvalidModelResponseError() from error
        if selected_tool.name == "get_batch_statistics":
            batch_id = arguments["batch_id"]
            if type(batch_id) is not int or not 0 < batch_id <= 2**31 - 1:
                raise InvalidModelResponseError()
        try:
            result = await selected_tool.ainvoke(arguments)
        except BatchNotFoundError:
            return AssistantResult(
                status="not_found",
                answer="Партия не найдена.",
                tools_called=[selected_tool.name],
            )
        if selected_tool.name == "find_batches":
            return self._search_result(result, arguments)
        return self._statistics_result(result, batch_id)

    @staticmethod
    def _statistics_result(result: object, batch_id: int) -> AssistantResult:
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
            tools_called=["get_batch_statistics"],
        )

    @staticmethod
    def _search_result(result: object, arguments: dict[str, object]) -> AssistantResult:
        try:
            search = BatchSearchResult.model_validate(result)
        except ValidationError as error:
            raise InvalidToolResultError() from error
        limit = arguments["limit"]
        if not isinstance(limit, int) or len(search.items) > limit:
            raise InvalidToolResultError()
        for item in search.items:
            if item.batch_number != arguments["batch_number"] or (
                arguments.get("batch_date") is not None
                and item.batch_date != arguments["batch_date"]
            ):
                raise InvalidToolResultError()
        if search.total == 0:
            return AssistantResult(
                status="not_found",
                answer="Партия не найдена.",
                search=search,
                tools_called=["find_batches"],
            )
        if search.total == 1:
            item = search.items[0]
            answer = f"Найдена партия №{item.batch_number} от {item.batch_date:%d.%m.%Y}, ID {item.id}."
        else:
            answer = f"Найдено партий: {search.total}. Уточните дату партии."
            if search.total > len(search.items):
                answer += f" Показаны первые {len(search.items)} совпадений."
        return AssistantResult(
            status="answered" if search.total == 1 else "needs_clarification",
            answer=answer,
            search=search,
            tools_called=["find_batches"],
        )
