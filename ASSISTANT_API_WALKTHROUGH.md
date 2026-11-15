# Ассистент FastAPI: полный код и объяснение

## Путь данных

HTTP → проверка клиентского ключа и схемы → AssistantService → адаптер модели → запрос инструмента → короткая сессия БД / кэш → проверка чисел → серверный ответ → JSON.

Во время ожидания модели сессия БД не открыта. Это проверяется тестом.

## Локальный запуск

В корневом `.env` бэкенда включите `ASSISTANT_LOCAL_ENABLED=true`. В текущем рабочем окружении он уже включён. Ключ провайдера и сертификат по-прежнему использует только FastAPI.

```bash
docker compose up -d --wait postgres redis
poetry run alembic upgrade head
poetry run uvicorn src.main:app --reload --host 127.0.0.1 --no-proxy-headers
```

Откройте http://127.0.0.1:8000/#assistant. Отдельного фронтенд-сервера нет. FastAPI отдаёт только frontend/public; браузер отправляет обычный fetch на относительный /api/v1/assistant/ask без ключей. API-роутеры и /health зарегистрированы раньше статических файлов.

Безключевой режим разрешён только при явно включённом флаге, loopback-адресе клиента и локальном Host. По умолчанию флаг выключен, вне локального режима сохраняется X-API-Key. Это режим разработки, а не пользовательская авторизация для публичного размещения. --no-proxy-headers не позволяет прокси-заголовкам менять адрес клиента в таком локальном запуске.

Настройки:

```python
assistant_local_enabled: bool = False
assistant_api_key: SecretStr | None = None
assistant_timeout_seconds: int = Field(default=15, gt=0, le=60)
```

Статические файлы подключаются в конце src/main.py:

```python
frontend_directory = Path(__file__).resolve().parent.parent / "frontend" / "public"
if settings.assistant_local_enabled and frontend_directory.is_dir():
    app.mount(
        "/", StaticFiles(directory=frontend_directory, html=True), name="frontend"
    )
```

## Код по слоям

### `src/api/v1/schemas/assistant.py`

Схемы HTTP: ограничения входа и контракт ответа.

```python
from pydantic import BaseModel, ConfigDict, Field

from src.application.dto.assistant import AssistantResult


class AssistantAskRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    question: str = Field(min_length=1, max_length=2000)


class AssistantAskResponse(AssistantResult):
    model_config = ConfigDict(from_attributes=True)
```

### `src/api/dependencies/assistant.py`

До сборки ассистента проверяется локальный доступ либо HTTP-ключ. Зависимость собирает модель, инструмент и сервис; управление SDK делегирует контексту интеграции.

```python
import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import APIKeyHeader

from src.application.ai.assistant_service import AssistantService
from src.application.ai.exceptions import AssistantNotConfiguredError
from src.application.ai.tools import create_find_batches_tool, create_statistics_tool
from src.core.assistant_dependencies import (
    batch_analytics_service,
    batch_search_service,
)
from src.core.config import settings
from src.integrations.llm.adapter import LangChainModelAdapter
from src.integrations.llm.factory import gigachat_model

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_assistant_key(
    request: Request,
    api_key: Annotated[str | None, Security(api_key_header)],
) -> None:
    if (
        settings.assistant_local_enabled
        and request.client is not None
        and request.client.host in {"127.0.0.1", "::1"}
        and request.url.hostname in {"127.0.0.1", "localhost", "::1"}
    ):
        return
    expected = settings.assistant_api_key
    if expected is None or not expected.get_secret_value():
        raise AssistantNotConfiguredError()
    if api_key is None or not secrets.compare_digest(
        api_key.encode(), expected.get_secret_value().encode()
    ):
        raise HTTPException(401, "Неверный ключ")


async def get_assistant_service(
    _authorized: Annotated[None, Depends(verify_assistant_key)],
) -> AsyncIterator[AssistantService]:
    async with gigachat_model(settings) as model:
        tools = [
            create_statistics_tool(batch_analytics_service),
            create_find_batches_tool(batch_search_service),
        ]
        yield AssistantService(
            LangChainModelAdapter(model, tools),
            tools,
            timeout_seconds=settings.assistant_timeout_seconds,
        )


AssistantServiceDep = Annotated[AssistantService, Depends(get_assistant_service)]
```

### `src/api/v1/routers/assistant.py`

Роутер принимает вопрос и готовый сервис, возвращает результат. Он не знает об SDK, Redis или SQLAlchemy.

```python
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
```

### `src/application/dto/assistant.py`

DTO результата и проверка согласованности чисел.

```python
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class FoundBatch(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int = Field(strict=True, gt=0, le=2**31 - 1)
    batch_number: int = Field(strict=True, gt=0, le=2**31 - 1)
    batch_date: date
    work_center_id: int = Field(strict=True, gt=0, le=2**31 - 1)
    is_closed: bool = Field(strict=True)


class BatchSearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[FoundBatch] = Field(max_length=10)
    total: int = Field(strict=True, ge=0)

    @model_validator(mode="after")
    def check_page(self) -> "BatchSearchResult":
        if self.total < len(self.items) or (self.total > 0 and not self.items):
            raise ValueError("Список партий не соответствует общему количеству")
        if len({item.id for item in self.items}) != len(self.items):
            raise ValueError("В списке повторяются ID партий")
        return self


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


class AssistantData(BatchStatisticsResult):
    batch_id: int = Field(gt=0, le=2**31 - 1)


class AssistantResult(BaseModel):
    status: Literal["answered", "not_found", "insufficient_data", "needs_clarification"]
    answer: str
    data: AssistantData | None = None
    search: BatchSearchResult | None = None
    tools_called: list[str] = Field(default_factory=list)
```

### `src/application/ai/ports.py`

Интерфейс модели для прикладного сервиса. Использует общие сообщения LangChain; это не полностью независимый от LangChain слой.

```python
from typing import Protocol

from langchain_core.messages import BaseMessage


class AssistantModel(Protocol):
    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage: ...
```

### `src/application/ai/assistant_service.py`

Сценарий одного вопроса: общий дедлайн, выбор и проверка инструмента, получение данных, серверный шаблон ответа. Без второго вызова модели.

```python
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
```

### `src/application/ai/tools.py`

Схема аргументов и разрешённая проекция статистики. Модель не может передать соединение БД или настройки.

```python
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import date

from langchain_core.tools import BaseTool, tool

from src.application.ai.schemas import BatchStatisticsArgs, FindBatchesArgs
from src.application.dto import BatchFilters
from src.application.dto.assistant import FoundBatch
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_service import BatchService


def create_statistics_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchAnalyticsService]],
) -> BaseTool:
    @tool(args_schema=BatchStatisticsArgs)
    async def get_batch_statistics(batch_id: int) -> dict[str, int]:
        """Получить количество изделий и остаток партии по-внутреннему ID."""
        async with service_factory() as service:
            statistics = await service.get_statistics(batch_id)
        return {
            "total": statistics.total_products,
            "aggregated": statistics.aggregated_products,
            "remaining": statistics.pending_products,
        }

    return get_batch_statistics


async def find_batches(
    service: BatchService,
    batch_number: int,
    batch_date: date | None = None,
    limit: int = 5,
) -> tuple[list[FoundBatch], int]:
    filters = BatchFilters(
        batch_number=batch_number,
        batch_date=batch_date,
    )

    batches, total = await service.list_batches(filters=filters, limit=limit, offset=0)

    items: list[FoundBatch] = []
    for batch in batches:
        item = FoundBatch.model_validate(batch)
        items.append(item)

    return items, total


def create_find_batches_tool(
    service_factory: Callable[[], AbstractAsyncContextManager[BatchService]],
) -> BaseTool:
    @tool("find_batches", args_schema=FindBatchesArgs)
    async def search_batches(
        batch_number: int,
        batch_date: date | None = None,
        limit: int = 5,
    ) -> dict[str, object]:
        """Найти партии по производственному номеру и необязательной дате.

        Номер партии отличается от внутреннего ID. Если найдено несколько
        партий, необходимо уточнить дату, а не выбирать первую.
        """
        async with service_factory() as service:
            items, total = await find_batches(
                service,
                batch_number=batch_number,
                batch_date=batch_date,
                limit=limit,
            )

        return {
            "items": [item.model_dump(mode="json") for item in items],
            "total": total,
        }

    return search_batches
```

### `src/application/ai/exceptions.py`

Именованные ошибки приложения, не содержащие HTTP-кодов и сообщений провайдера.

```python
class AssistantNotConfiguredError(Exception):
    def __init__(self) -> None:
        super().__init__("Ассистент не настроен")


class LLMUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Модель временно недоступна")


class AssistantTimeoutError(Exception):
    def __init__(self) -> None:
        super().__init__("Истекло время обработки вопроса")


class InvalidModelResponseError(Exception):
    def __init__(self) -> None:
        super().__init__("Модель вернула некорректный запрос инструмента")


class InvalidToolResultError(Exception):
    def __init__(self) -> None:
        super().__init__("Не удалось получить проверенную статистику")


class AssistantDataUnavailableError(Exception):
    def __init__(self) -> None:
        super().__init__("Источник данных ассистента временно недоступен")
```

### `src/integrations/llm/adapter.py`

Адаптер переводит ожидаемые ошибки HTTP и SDK в ошибки приложения. Обычные ValueError и TypeError не перехватываются.

```python
import httpx
from gigachat.exceptions import GigaChatException
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage
from langchain_core.tools import BaseTool
from pydantic import ValidationError

from src.application.ai.exceptions import (
    AssistantTimeoutError,
    InvalidModelResponseError,
    LLMUnavailableError,
)


class LangChainModelAdapter:
    """Translate provider failures into application exceptions."""

    def __init__(self, model: BaseChatModel, tools: list[BaseTool]) -> None:
        self.model = model.bind_tools(tools)

    async def ainvoke(self, messages: list[BaseMessage]) -> BaseMessage:
        try:
            return await self.model.ainvoke(messages)
        except httpx.TimeoutException as error:
            raise AssistantTimeoutError() from error
        except (httpx.HTTPError, GigaChatException, OSError) as error:
            raise LLMUnavailableError() from error
        except ValidationError as error:
            raise InvalidModelResponseError() from error
```

### `src/integrations/llm/factory.py`

Создание и жизненный цикл модели принадлежат интеграции. Автоматические повторы SDK отключены. Единственное обращение к внутреннему _client находится здесь. Ошибка закрытия не подменяет исходную ошибку или отмену запроса.

```python
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from gigachat.exceptions import GigaChatException
from langchain_gigachat import GigaChat
from pydantic import ValidationError

from src.application.ai.exceptions import (
    AssistantNotConfiguredError,
    LLMUnavailableError,
)
from src.core.config import Settings

logger = logging.getLogger(__name__)


def create_gigachat(settings: Settings) -> GigaChat:
    """Create a model from application settings without sending a request."""
    if (
        settings.gigachat_auth_key is None
        or not settings.gigachat_auth_key.get_secret_value()
    ):
        raise AssistantNotConfiguredError()

    return GigaChat(
        credentials=settings.gigachat_auth_key.get_secret_value(),
        scope="GIGACHAT_API_PERS",
        model=settings.gigachat_model,
        timeout=settings.gigachat_timeout_seconds,
        base_url="https://api.giga.chat/v1",
        max_tokens=100,
        max_retries=0,
        verify_ssl_certs=True,
        ca_bundle_file=settings.gigachat_ca_bundle_file,
    )


@asynccontextmanager
async def gigachat_model(settings: Settings) -> AsyncIterator[GigaChat]:
    """Own the provider client lifecycle inside the integration boundary."""
    try:
        model = create_gigachat(settings)
        client = model._client
    except (ValidationError, OSError) as error:
        raise AssistantNotConfiguredError() from error
    failed = True
    try:
        yield model
        failed = False
    finally:
        try:
            await client.aclose()
        except (httpx.HTTPError, GigaChatException, OSError) as error:
            if not failed:
                raise LLMUnavailableError() from error
            # Preserve the primary error, including cancellation and programming bugs.
            logger.warning("Cannot close LLM client after a failed operation")
```

### `src/core/assistant_dependencies.py`

Сборка инфраструктуры: сессия открывается только внутри инструмента. Сетевые ошибки БД/Redis переводятся в исключение приложения, ошибки программирования SQL остаются видимыми.

```python
"""Short-lived dependencies for assistant tools."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from src.application.ai.exceptions import AssistantDataUnavailableError
from src.application.dto.analytics import BatchAnalyticsSnapshot
from src.application.services.batch_analytics_service import BatchAnalyticsService
from src.application.services.batch_service import BatchService
from src.core.batch_service_factory import build_batch_service
from src.core.config import settings
from src.core.database import async_session_maker
from src.data.unit_of_work import UnitOfWork
from src.storage.analytics_cache import AnalyticsCache
from src.storage.redis import create_redis_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def _assistant_resources() -> AsyncIterator[tuple[UnitOfWork, Redis]]:
    """Keep database and Redis resources within one tool execution."""
    redis = create_redis_client()
    failed = True
    try:
        async with async_session_maker() as session:
            yield UnitOfWork(session), redis
        failed = False
    except (
        OperationalError,
        InterfaceError,
        DisconnectionError,
        PoolTimeoutError,
        RedisError,
        OSError,
    ) as error:
        raise AssistantDataUnavailableError() from error
    finally:
        try:
            await redis.aclose()
        except (RedisError, OSError) as error:
            if not failed:
                raise AssistantDataUnavailableError() from error
            logger.warning(
                "Cannot close analytics cache client after a failed operation"
            )


@asynccontextmanager
async def batch_analytics_service() -> AsyncIterator[BatchAnalyticsService]:
    async with _assistant_resources() as (uow, redis):
        yield BatchAnalyticsService(
            uow,
            AnalyticsCache(
                redis,
                BatchAnalyticsSnapshot,
                settings.batch_statistics_cache_ttl_seconds,
            ),
        )


@asynccontextmanager
async def batch_search_service() -> AsyncIterator[BatchService]:
    async with _assistant_resources() as (uow, redis):
        yield build_batch_service(uow, redis)
```

### `src/api/exception_handlers.py`

Общий HTTP-слой сопоставляет именованные исключения с кодами ответа. Соответствует существующему механизму проекта.

```python
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from src.application.ai.exceptions import (
    AssistantDataUnavailableError,
    AssistantNotConfiguredError,
    AssistantTimeoutError,
    InvalidModelResponseError,
    InvalidToolResultError,
    LLMUnavailableError,
)
from src.application.exceptions import (
    ObjectStorageUnavailableError,
    ReportNotFoundError,
    WebhookDeliveryNotFoundError,
    WebhookSubscriptionNotFoundError,
)
from src.domain.exceptions.batch import (
    BatchAlreadyExistsError,
    BatchClosedError,
    BatchComparisonInvalidError,
    BatchHasProductsError,
    BatchInvalidShiftPeriodError,
    BatchNotFoundError,
)
from src.domain.exceptions.product import (
    ProductAlreadyAggregatedError,
    ProductAlreadyExistsError,
    ProductBatchMismatchError,
    ProductNotFoundError,
)
from src.domain.exceptions.work_center import (
    WorkCenterAlreadyExistsError,
    WorkCenterHasBatchesError,
    WorkCenterNotFoundError,
)
from src.integrations.webhooks.url_policy import UnsafeWebhookUrlError

ERROR_STATUS_CODES: dict[type[Exception], int] = {
    AssistantNotConfiguredError: status.HTTP_503_SERVICE_UNAVAILABLE,
    LLMUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    AssistantTimeoutError: status.HTTP_504_GATEWAY_TIMEOUT,
    InvalidModelResponseError: status.HTTP_503_SERVICE_UNAVAILABLE,
    InvalidToolResultError: status.HTTP_503_SERVICE_UNAVAILABLE,
    AssistantDataUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    UnsafeWebhookUrlError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    WorkCenterAlreadyExistsError: status.HTTP_409_CONFLICT,
    WorkCenterNotFoundError: status.HTTP_404_NOT_FOUND,
    WorkCenterHasBatchesError: status.HTTP_409_CONFLICT,
    BatchAlreadyExistsError: status.HTTP_409_CONFLICT,
    BatchNotFoundError: status.HTTP_404_NOT_FOUND,
    BatchClosedError: status.HTTP_409_CONFLICT,
    BatchComparisonInvalidError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    BatchHasProductsError: status.HTTP_409_CONFLICT,
    BatchInvalidShiftPeriodError: status.HTTP_422_UNPROCESSABLE_CONTENT,
    ProductAlreadyExistsError: status.HTTP_409_CONFLICT,
    ProductAlreadyAggregatedError: status.HTTP_409_CONFLICT,
    ProductBatchMismatchError: status.HTTP_409_CONFLICT,
    ProductNotFoundError: status.HTTP_404_NOT_FOUND,
    ReportNotFoundError: status.HTTP_404_NOT_FOUND,
    ObjectStorageUnavailableError: status.HTTP_503_SERVICE_UNAVAILABLE,
    WebhookSubscriptionNotFoundError: status.HTTP_404_NOT_FOUND,
    WebhookDeliveryNotFoundError: status.HTTP_404_NOT_FOUND,
}


async def domain_error_handler(
    _request: Request,
    exc: Exception,
) -> JSONResponse:
    return JSONResponse(
        status_code=ERROR_STATUS_CODES[type(exc)],
        content={"detail": str(exc)},
    )


def register_exception_handlers(app: FastAPI) -> None:
    for error_type in ERROR_STATUS_CODES:
        app.add_exception_handler(error_type, domain_error_handler)
```

### `scripts/check_gigachat.py`

Проверочный скрипт использует те же интеграцию, сервис и инструмент. SDK закрывается контекстом интеграции, пул БД — при завершении скрипта.

```python
import asyncio

from src.application.ai.assistant_service import AssistantService
from src.application.ai.tools import create_find_batches_tool, create_statistics_tool
from src.core.assistant_dependencies import (
    batch_analytics_service,
    batch_search_service,
)
from src.core.config import settings
from src.core.database import dispose_engine
from src.integrations.llm.adapter import LangChainModelAdapter
from src.integrations.llm.factory import gigachat_model


async def main() -> None:
    try:
        async with gigachat_model(settings) as model:
            tools = [
                create_statistics_tool(batch_analytics_service),
                create_find_batches_tool(batch_search_service),
            ]
            assistant = AssistantService(
                LangChainModelAdapter(model, tools),
                tools,
                timeout_seconds=settings.assistant_timeout_seconds,
            )
            result = await assistant.ask("Сколько изделий осталось в партии с ID 1?")
            print(result.answer)
    finally:
        await dispose_engine()


if __name__ == "__main__":
    asyncio.run(main())
```

### `scripts/llm_dependencies.py`

Совместимый импорт для старого пути; src не зависит от scripts.

```python
"""Compatibility import for local scripts."""

from src.core.assistant_dependencies import batch_analytics_service

__all__ = ["batch_analytics_service"]
```

## Границы текущего этапа

Одна партия по внутреннему ID, локальный доступ без ключа либо общий клиентский ключ на чтение, самодостаточные вопросы. Ассистент использует действующий IP-лимитер проекта, который требует Redis. Отдельный лимит по ключу, бюджет, кэш ответов, trace_id/as_of и Langfuse из LLM_ARCHITECTURE.md ещё не реализованы. Сейчас это первая локальная версия API, не завершение всей A1.

Проверки: tests/unit/test_assistant_api.py, test_assistant_service.py, test_assistant_dependencies.py, test_llm_adapter.py, test_llm_lifecycle.py. Внешняя модель и БД подменяются, реальные запросы к провайдеру тесты не делают.

### `src/application/ai/schemas.py`

Схемы аргументов инструментов. Отдельны от HTTP-схем и DTO результатов.

```python
"""Validated arguments for production assistant tools."""

from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class BatchStatisticsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: int = Field(gt=0, le=2**31 - 1)


class FindBatchesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    batch_number: int = Field(strict=True, ge=1, le=2**31 - 1)
    batch_date: date | None = None
    limit: int = Field(default=5, strict=True, ge=1, le=10)
```

## Выбор двух инструментов

Модель получает get_batch_statistics и find_batches. Сервис хранит инструменты в словаре по именам, проверяет имя и аргументы, исполняет ровно один инструмент и формирует ответ на сервере. Статистика находится в data, результат поиска — в search (items и total). total=0 даёт not_found, total=1 — answered, total>1 — needs_clarification. Показ одной записи при limit=1 не означает однозначного совпадения. Числа и найденные партии из свободного текста модели не используются.

Пока это два отдельных действия. После поиска кнопка интерфейса подставляет самостоятельный вопрос о статистике ID. Цепочка нескольких инструментов в одном вопросе ещё не реализована.
