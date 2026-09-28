from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.exception_handlers import register_exception_handlers
from src.api.v1.routers import api_v1_router
from src.core.database import dispose_engine
from src.core.logging import configure_logging
from src.storage.redis import close_redis


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

app.include_router(
    api_v1_router,
)


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
