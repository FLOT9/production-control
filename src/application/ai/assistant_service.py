import asyncio
import json
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from pydantic import TypeAdapter, ValidationError

from src.application.ai.aggregation_day import resolve_aggregation_range
from src.application.ai.exceptions import (
    AssistantTimeoutError,
    InvalidModelResponseError,
    InvalidToolResultError,
    LLMUnavailableError,
)
from src.application.ai.ports import AssistantModel
from src.application.ai.schemas import (
    AggregationDayArgs,
    BatchStatisticsArgs,
    DashboardArgs,
    FindBatchesArgs,
)
from src.application.dto.analytics import BatchComparisonRequest
from src.application.dto.assistant import (
    AggregationDayToolResult,
    AssistantData,
    AssistantResult,
    BatchComparisonToolItem,
    BatchCountResult,
    BatchSearchResult,
    BatchStatisticsToolResult,
    DashboardToolResult,
)
from src.core.config import settings
from src.domain.exceptions.batch import BatchNotFoundError
from src.domain.exceptions.work_center import WorkCenterNotFoundError

comparison_items = TypeAdapter(list[BatchComparisonToolItem])
WORK_CENTER_ID_HINT = "Укажите внутренний ID цеха, например «цех с ID 2»."
EXPLICIT_ID = re.compile(r"\bID\s*[:=#№]?\s*([0-9]{1,10})\b", re.IGNORECASE)


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
        if self.tools.keys() - {
            "get_batch_statistics",
            "find_batches",
            "compare_batches",
            "get_dashboard",
            "count_aggregated_on",
        }:
            raise ValueError("Не поддерживается обработка результата инструмента")
        self.model = model
        self.timeout_seconds = timeout_seconds

    async def ask(self, question: str) -> AssistantResult:
        try:
            async with asyncio.timeout(self.timeout_seconds):
                return await self._ask(question, now=datetime.now(UTC))
        except TimeoutError as error:
            raise AssistantTimeoutError() from error

    async def _ask(self, question: str, *, now: datetime) -> AssistantResult:
        messages: list[BaseMessage] = [
            SystemMessage(
                content=(
                    "Ты ассистент производства. "
                    "Выбери не более одного инструмента за ответ. "
                    "Если после find_batches получен результат с batch_id и запрошены "
                    "показатели партии, вызови get_batch_statistics с этим batch_id. "
                    "Для первого вызова определи тип идентификатора.\n"
                    "1. «№123» или «номер партии 123» означает batch_number=123. "
                    "Вызови find_batches, даже если вопрос про остаток или количество изделий. "
                    "Число после «№» запрещено передавать в batch_id. "
                    "Если указана дата, передай её в batch_date в формате ГГГГ-ММ-ДД. "
                    "Для показателей конкретной партии передай include_statistics=true, "
                    "для обычного поиска — include_statistics=false.\n"
                    "Для списка партий и вопросов «сколько партий» используй find_batches. "
                    "Укажи нужные фильтры: batch_date или date_from/date_to, внутренний "
                    "work_center_id, shift, is_closed=false для открытых или true для закрытых. "
                    "Для количества партий передай count_only=true. Например, «Сколько "
                    "открытых партий в цехе с ID 2?» → "
                    "find_batches(work_center_id=2, is_closed=false, count_only=true).\n"
                    "2. Если пользователь явно написал «ID 123» и просит показатели, "
                    "вызови get_batch_statistics(batch_id=123) для одной партии.\n"
                    "3. Для сравнения партий по внутренним ID вызывай compare_batches. "
                    "«Сравни остатки в партиях с ID 1 и 2» → "
                    "compare_batches(batch_ids=[1, 2]).\n"
                    "4. Для сводки по дате партий вызывай get_dashboard. "
                    "Если указаны внутренний ID цеха или смена, передай work_center_id и shift. "
                    "Например, «Сколько сейчас агрегировано изделий в партиях от 5 сентября "
                    '2026 года?» → get_dashboard(date_from="2026-09-05", date_to="2026-09-05"). '
                    "5. Для подсчёта по дате самой операции за день или период "
                    "вызывай count_aggregated_on. "
                    "«Сколько изделий агрегировали 5 сентября 2026 года?» → "
                    'count_aggregated_on(day="2026-09-05"). '
                    'Для «сегодня» передай day="today", для «вчера» — day="yesterday". '
                    "«Сколько изделий агрегировали вчера?» → "
                    'count_aggregated_on(day="yesterday"). '
                    "Если явно указан внутренний ID цеха, передай его в work_center_id. "
                    "«Сколько изделий вчера агрегировали в цехе с ID 12?» → "
                    'count_aggregated_on(day="yesterday", work_center_id=12). '
                    "Для диапазона передай date_from и date_to включительно. "
                    "«Сколько изделий агрегировали за прошлую неделю?» → "
                    'count_aggregated_on(period="last_week"). '
                    "Дата, диапазон и last_week взаимоисключающие. Если цех указан только "
                    "по названию или номеру, верни NEED_WORK_CENTER_ID без инструмента. "
                    "Без указанного цеха опусти work_center_id.\n"
                    "Примеры:\n"
                    "«Сколько изделий осталось в партии с ID 17?» → "
                    "get_batch_statistics(batch_id=17).\n"
                    "«Найди партию №41 от 10 ноября 2026 года» → "
                    'find_batches(batch_number=41, batch_date="2026-11-10", '
                    "include_statistics=false).\n"
                    "«Сколько изделий осталось в партии №2026111001 от 10 ноября 2026 года?» → "
                    'find_batches(batch_number=2026111001, batch_date="2026-11-10", '
                    "include_statistics=true).\n"
                    "На вопросы вне производственной статистики верни только OUT_OF_SCOPE "
                    "без вызова инструмента. Например, «Какая завтра погода?» → OUT_OF_SCOPE. "
                    "Если для подсчёта агрегаций цех задан только по названию или номеру, "
                    "верни только NEED_WORK_CENTER_ID. Например, «Сколько изделий вчера "
                    "агрегировали в цехе Сборка?» → NEED_WORK_CENTER_ID. "
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
            return self._answer_without_tool(response)
        if len(response.tool_calls) != 1:
            raise InvalidModelResponseError()

        tool_call = response.tool_calls[0]
        selected_tool = self.tools.get(tool_call["name"])
        if selected_tool is None:
            raise InvalidModelResponseError()
        if selected_tool.name == "get_batch_statistics":
            try:
                statistics_args = BatchStatisticsArgs.model_validate(tool_call["args"])
            except ValidationError as error:
                raise InvalidModelResponseError() from error
            return await self._read_statistics(statistics_args.batch_id)
        if selected_tool.name == "compare_batches":
            return await self._compare_batches(selected_tool, tool_call["args"])
        if selected_tool.name == "get_dashboard":
            return await self._get_dashboard(selected_tool, tool_call["args"])
        if selected_tool.name == "count_aggregated_on":
            return await self._count_aggregated_on(
                selected_tool, tool_call["args"], now=now, question=question
            )

        try:
            search_args = FindBatchesArgs.model_validate(tool_call["args"])
        except ValidationError as error:
            raise InvalidModelResponseError() from error
        try:
            result = await selected_tool.ainvoke(
                search_args.model_dump(exclude_defaults=True)
            )
            if search_args.count_only:
                count = BatchCountResult.model_validate(result)
                return AssistantResult(
                    status="answered",
                    answer=f"Партий по заданным фильтрам: {count.total}.",
                    tools_called=["find_batches"],
                )
            search = BatchSearchResult.model_validate(result)
        except ValidationError as error:
            raise InvalidToolResultError() from error

        if len(search.items) > search_args.limit or any(
            (
                search_args.batch_number is not None
                and item.batch_number != search_args.batch_number
            )
            or (
                search_args.batch_date is not None
                and item.batch_date != search_args.batch_date
            )
            or (
                search_args.date_from is not None
                and item.batch_date < search_args.date_from
            )
            or (
                search_args.date_to is not None
                and item.batch_date > search_args.date_to
            )
            or (
                search_args.work_center_id is not None
                and item.work_center_id != search_args.work_center_id
            )
            or (search_args.shift is not None and item.shift != search_args.shift)
            or (
                search_args.is_closed is not None
                and item.is_closed != search_args.is_closed
            )
            for item in search.items
        ):
            raise InvalidToolResultError()

        if search.total == 1 and search_args.include_statistics:
            batch_id = await self._select_statistics_batch_id(
                messages, response, search.items[0].id
            )
            return await self._read_statistics(batch_id, search=search)
        return self._search_result(
            search, clarify_number=search_args.batch_number is not None
        )

    async def _select_statistics_batch_id(
        self, messages: list[BaseMessage], first_response: AIMessage, found_id: int
    ) -> int:
        search_call = first_response.tool_calls[0]
        call_id = search_call.get("id")
        if not call_id or "get_batch_statistics" not in self.tools:
            return found_id

        follow_up = [
            *messages,
            first_response,
            ToolMessage(
                name=search_call["name"],
                tool_call_id=call_id,
                content=json.dumps({"batch_id": found_id}),
            ),
        ]
        try:
            response = await self.model.ainvoke(follow_up)
        except (AssistantTimeoutError, InvalidModelResponseError, LLMUnavailableError):
            return found_id
        if (
            not isinstance(response, AIMessage)
            or response.invalid_tool_calls
            or len(response.tool_calls) != 1
        ):
            return found_id
        call = response.tool_calls[0]
        if call["name"] != "get_batch_statistics":
            return found_id
        try:
            request = BatchStatisticsArgs.model_validate(call["args"])
        except ValidationError:
            return found_id
        return request.batch_id if request.batch_id == found_id else found_id

    @staticmethod
    def _answer_without_tool(response: AIMessage) -> AssistantResult:
        marker = response.content.strip() if isinstance(response.content, str) else ""
        if marker == "OUT_OF_SCOPE":
            return AssistantResult(
                status="out_of_scope",
                answer="Я могу помочь с партиями и производственной статистикой.",
            )
        if marker == "NEED_WORK_CENTER_ID":
            return AssistantResult(
                status="insufficient_data",
                answer=WORK_CENTER_ID_HINT,
            )
        return AssistantResult(
            status="insufficient_data",
            answer=(
                "Для подсчёта по цеху укажите его внутренний ID. "
                "Для поиска партии укажите её ID либо номер и дату."
            ),
        )

    async def _count_aggregated_on(
        self, tool: BaseTool, args: dict[str, object], *, now: datetime, question: str
    ) -> AssistantResult:
        try:
            request = AggregationDayArgs.model_validate(args)
        except ValidationError as error:
            raise InvalidModelResponseError() from error
        if request.work_center_id is not None and request.work_center_id not in {
            int(value) for value in EXPLICIT_ID.findall(question)
        }:
            return AssistantResult(
                status="insufficient_data", answer=WORK_CENTER_ID_HINT
            )
        start, end = resolve_aggregation_range(
            request, now, ZoneInfo(settings.production_timezone)
        )
        date_args = (
            {"day": start} if start == end else {"date_from": start, "date_to": end}
        )
        period = (
            f"{start:%d.%m.%Y}"
            if start == end
            else f"С {start:%d.%m.%Y} по {end:%d.%m.%Y}"
        )
        try:
            result = await tool.ainvoke(
                {**date_args, "work_center_id": request.work_center_id}
            )
            counts = AggregationDayToolResult.model_validate(result)
        except WorkCenterNotFoundError:
            return AssistantResult(
                status="not_found",
                answer=f"Цех с ID {request.work_center_id} не найден.",
                tools_called=[tool.name],
            )
        except ValidationError as error:
            raise InvalidToolResultError() from error
        count = counts.aggregated_products
        unknown = counts.unknown_work_center_count
        if request.work_center_id is None:
            if unknown is not None:
                raise InvalidToolResultError()
            answer = f"{period} агрегировали {count} изд. по всем цехам."
        else:
            if unknown is None:
                raise InvalidToolResultError()
            answer = (
                f"{period} в цехе с ID {request.work_center_id} "
                f"подтверждено {count} агрегированных изд."
            )
            if unknown:
                answer += (
                    f" У {unknown} изд. за {'этот день' if start == end else 'этот период'} цех неизвестен. "
                    "Точный итог по цеху недоступен."
                )
        return AssistantResult(
            status="answered",
            answer=answer,
            tools_called=[tool.name],
        )

    async def _get_dashboard(
        self, tool: BaseTool, args: dict[str, object]
    ) -> AssistantResult:
        try:
            request = DashboardArgs.model_validate(args)
        except ValidationError as error:
            raise InvalidModelResponseError() from error
        try:
            result = await tool.ainvoke(request.model_dump())
            dashboard = DashboardToolResult.model_validate(result)
        except ValidationError as error:
            raise InvalidToolResultError() from error
        scope = ""
        if request.work_center_id is not None:
            scope += f" Цех с ID {request.work_center_id}."
        if request.shift is not None:
            scope += f" Смена: {request.shift}."
        return AssistantResult(
            status="answered",
            answer=(
                f"Дата партии с {request.date_from:%d.%m.%Y} по {request.date_to:%d.%m.%Y}."
                f"{scope} Сейчас агрегировано: {dashboard.aggregated_products} изд."
            ),
            tools_called=[tool.name],
        )

    async def _compare_batches(
        self, tool: BaseTool, args: dict[str, object]
    ) -> AssistantResult:
        try:
            request = BatchComparisonRequest.model_validate(args)
        except ValidationError as error:
            raise InvalidModelResponseError() from error
        try:
            result = await tool.ainvoke(request.model_dump())
        except BatchNotFoundError:
            return AssistantResult(
                status="not_found",
                answer="Одна из партий не найдена.",
                tools_called=[tool.name],
            )
        try:
            items = comparison_items.validate_python(result)
        except ValidationError as error:
            raise InvalidToolResultError() from error
        if [item.batch_id for item in items] != request.batch_ids:
            raise InvalidToolResultError()

        lines = [
            f"ID {item.batch_id}: всего {item.total} изд., агрегировано {item.aggregated}, "
            f"осталось {item.remaining}, выполнение {item.aggregation_percent:g}%, "
            f"темп за полную смену {item.products_per_hour:g} изд./ч."
            for item in items
        ]
        return AssistantResult(
            status="answered",
            answer="\n".join(lines),
            tools_called=[tool.name],
        )

    async def _read_statistics(
        self, batch_id: int, *, search: BatchSearchResult | None = None
    ) -> AssistantResult:
        tool = self.tools.get("get_batch_statistics")
        if tool is None:
            raise InvalidModelResponseError()
        tools_called = (
            ["find_batches", tool.name] if search is not None else [tool.name]
        )
        try:
            result = await tool.ainvoke({"batch_id": batch_id})
        except BatchNotFoundError:
            return AssistantResult(
                status="not_found",
                answer="Партия не найдена.",
                tools_called=tools_called,
            )
        try:
            statistics = BatchStatisticsToolResult.model_validate(result)
        except ValidationError as error:
            raise InvalidToolResultError() from error
        label = f"Партия с ID {batch_id}"
        if search is not None:
            batch = search.items[0]
            label = f"Партия №{batch.batch_number} от {batch.batch_date:%d.%m.%Y} (ID {batch_id})"
        answer = (
            f"{label}: всего {statistics.total} изделий, "
            f"агрегировано {statistics.aggregated}, осталось {statistics.remaining}."
        )
        if statistics.aggregation_percent is not None:
            answer += f" Выполнение: {statistics.aggregation_percent:g}%."
            if statistics.products_per_hour is None:
                answer += " Текущий темп недоступен."
            else:
                answer += f" Текущий темп: {statistics.products_per_hour:g} изд./ч."
        return AssistantResult(
            status="answered",
            answer=answer,
            data=AssistantData(
                batch_id=batch_id,
                **statistics.model_dump(
                    exclude={"aggregation_percent", "products_per_hour"}
                ),
            ),
            tools_called=tools_called,
        )

    @staticmethod
    def _search_result(
        search: BatchSearchResult, *, clarify_number: bool
    ) -> AssistantResult:
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
            answer = f"Найдено партий: {search.total}."
            if clarify_number:
                answer += " Уточните дату партии."
            if search.total > len(search.items):
                answer += f" Показаны первые {len(search.items)} совпадений."
            if not clarify_number:
                lines = [
                    f"№{item.batch_number} от {item.batch_date:%d.%m.%Y}, ID {item.id}"
                    for item in search.items
                ]
                answer += "\n" + "\n".join(lines)
        return AssistantResult(
            status="needs_clarification"
            if search.total > 1 and clarify_number
            else "answered",
            answer=answer,
            search=search,
            tools_called=["find_batches"],
        )
