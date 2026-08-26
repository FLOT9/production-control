from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
