import logging

from redis.exceptions import RedisError
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from src.storage.rate_limiter import RateLimit, RedisRateLimiter

logger = logging.getLogger(__name__)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
BACKGROUND_PATHS = {
    "/api/v1/batches/import/csv",
    "/api/v1/batches/export/csv",
    "/api/v1/products/aggregate-bulk",
    "/api/v1/reports/production-summary",
}


class RateLimitMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        limiter: RedisRateLimiter,
        *,
        enabled: bool = True,
        write_limit: int = 60,
        background_limit: int = 10,
    ) -> None:
        self.app = app
        self.limiter = limiter
        self.enabled = enabled
        self.write_limit = write_limit
        self.background_limit = background_limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.enabled or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"].rstrip("/")
        if not path.startswith("/api/v1/") or scope["method"] not in WRITE_METHODS:
            await self.app(scope, receive, send)
            return

        limits = [RateLimit("writes", self.write_limit)]
        if scope["method"] == "POST" and path in BACKGROUND_PATHS:
            limits.append(RateLimit("background", self.background_limit))

        # Use the server-resolved peer, never arbitrary forwarded headers.
        client = scope.get("client")
        client_id = client[0] if client else "unknown"
        try:
            decision = await self.limiter.check(client_id, limits)
        except RedisError:
            logger.warning("Rate limiter Redis is unavailable", exc_info=True)
            response = JSONResponse(
                status_code=503,
                content={"detail": "Rate limiter is temporarily unavailable"},
            )
            await response(scope, receive, send)
            return

        if not decision.allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests"},
                headers={"Retry-After": str(decision.retry_after_seconds)},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
