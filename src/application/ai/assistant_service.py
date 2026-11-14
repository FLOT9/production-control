import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domain.exceptions.batch import BatchNotFoundError


class BatchStatisticsResult(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    total: int = Field(ge=0)
    aggregated: int = Field(ge=0)
    remaining: int = Field(ge=0)

    @model_validator(mode="after")
    def check_counts(self) -> "BatchStatisticsResult":
        if self.aggregated + self.remaining != self.total:
            raise ValueError("Показатели партии не согласованы")
        return self


class AssistantService:
    def __init__(self, model: BaseChatModel, statistics_tool: BaseTool) -> None:
        self.tool = statistics_tool
        self.model = model.bind_tools([statistics_tool])

    async def ask(self, question: str) -> str:
        messages: list[BaseMessage] = [
            SystemMessage(
                content=(
                    "Ты ассистент производства. "
                    "Для получения показателей партий используй доступный инструмент. "
                    "Не выдумывай показатели."
                )
            ),
            HumanMessage(content=question),
        ]

        response = await self.model.ainvoke(messages)
        if not isinstance(response, AIMessage):
            raise TypeError("Ожидалось сообщение модели AIMessage")
        if not response.tool_calls:
            return "Недостаточно данных: модель не запросила статистику партии."

        if len(response.tool_calls) != 1:
            raise ValueError("Ассистент пока поддерживает одну партию за запрос")

        messages.append(response)
        for tool_call in response.tool_calls:
            if tool_call["name"] != self.tool.name:
                raise ValueError("Неизвестный инструмент")

            batch_id = tool_call["args"].get("batch_id")
            if type(batch_id) is not int or not 0 < batch_id <= 2**31 - 1:
                raise ValueError("Ожидался положительный int32 batch_id")

            try:
                result = await self.tool.ainvoke(tool_call["args"])
            except BatchNotFoundError:
                return "Партия не найдена."

            statistics = BatchStatisticsResult.model_validate(result)
            messages.append(
                ToolMessage(
                    content=json.dumps(statistics.model_dump(), ensure_ascii=False),
                    tool_call_id=tool_call["id"],
                    name=tool_call["name"],
                )
            )

        final_response = await self.model.ainvoke(messages)
        if not isinstance(final_response, AIMessage):
            raise TypeError("Ожидалось сообщение модели AIMessage")
        if final_response.tool_calls:
            raise RuntimeError("Ассистент пока поддерживает один раунд инструментов")
        # Свободный текст модели не является источником производственных показателей.
        return (
            f"Партия с ID {batch_id}: всего {statistics.total} изделий, "
            f"агрегировано {statistics.aggregated}, осталось {statistics.remaining}."
        )
