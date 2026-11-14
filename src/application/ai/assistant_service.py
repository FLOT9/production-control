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

from src.domain.exceptions.batch import BatchNotFoundError


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
            return self._text(response)

        messages.append(response)
        for tool_call in response.tool_calls:
            if tool_call["name"] != self.tool.name:
                raise ValueError("Неизвестный инструмент")

            try:
                result = await self.tool.ainvoke(tool_call["args"])
            except BatchNotFoundError:
                return "Партия не найдена."

            messages.append(
                ToolMessage(
                    content=json.dumps(result, ensure_ascii=False),
                    tool_call_id=tool_call["id"],
                )
            )

        final_response = await self.model.ainvoke(messages)
        if not isinstance(final_response, AIMessage):
            raise TypeError("Ожидалось сообщение модели AIMessage")
        if final_response.tool_calls:
            raise RuntimeError("Ассистент пока поддерживает один раунд инструментов")
        return self._text(final_response)

    @staticmethod
    def _text(message: AIMessage) -> str:
        if not isinstance(message.content, str):
            raise TypeError("Ожидался текстовый ответ модели")
        return message.content
