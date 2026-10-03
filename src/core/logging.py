import logging
import sys

from loguru import logger

from src.core.config import settings


class InterceptHandler(logging.Handler):
    """Forward standard-library logs to Loguru without losing tracebacks."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            level: str | int = logger.level(record.levelname).name
        except ValueError:
            level = record.levelno

        logger.bind(source_logger=record.name).opt(exception=record.exc_info).log(
            level, record.getMessage()
        )


def configure_logging() -> None:
    """Write application, Uvicorn and Celery logs as JSON lines."""

    level = "DEBUG" if settings.debug else "INFO"
    logger.remove()
    logger.add(sys.stderr, level=level, serialize=True, backtrace=False, diagnose=False)

    handler = InterceptHandler()
    logging.basicConfig(handlers=[handler], level=level, force=True)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False
