from contextlib import asynccontextmanager

from fastapi import FastAPI

from src.api.exception_handlers import register_exception_handlers
from src.api.v1.routers import api_v1_router
from src.core.database import dispose_engine


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield

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
