from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.exception_handlers import register_exception_handlers
from src.api.middleware.rate_limit import RateLimitMiddleware
from src.api.v1.routers import api_v1_router
from src.core.config import settings
from src.core.database import dispose_engine
from src.core.logging import configure_logging
from src.storage.rate_limiter import RedisRateLimiter
from src.storage.redis import close_redis, redis_client


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    try:
        yield
    finally:
        await close_redis()
        await dispose_engine()


app = FastAPI(
    title="Production Control API",
    version="0.1.0",
    lifespan=lifespan,
)

register_exception_handlers(app)

app.add_middleware(
    RateLimitMiddleware,
    limiter=RedisRateLimiter(redis_client, settings.rate_limit_window_seconds),
    enabled=settings.rate_limit_enabled,
    write_limit=settings.rate_limit_write_requests,
    background_limit=settings.rate_limit_background_requests,
)

app.include_router(
    api_v1_router,
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
