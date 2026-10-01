from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from redis.exceptions import ConnectionError
from starlette.types import Scope

from src.api.middleware.rate_limit import BACKGROUND_PATHS, RateLimitMiddleware
from src.storage.rate_limiter import RateLimit, RateLimitDecision


class RateLimitMiddlewareTests(IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.app = AsyncMock()
        self.limiter = AsyncMock()
        self.limiter.check.return_value = RateLimitDecision(True, 0)
        self.receive = AsyncMock()
        self.send = AsyncMock()
        self.middleware = RateLimitMiddleware(self.app, self.limiter)
        self.scope: Scope = {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/batches",
            "client": ("127.0.0.1", 1234),
            "headers": [(b"x-forwarded-for", b"attacker")],
        }

    async def test_allowed_write_reaches_handler_with_peer_ip(self) -> None:
        await self.middleware(self.scope, self.receive, self.send)
        self.limiter.check.assert_awaited_once_with(
            "127.0.0.1", [RateLimit("writes", 60)]
        )
        self.app.assert_awaited_once_with(self.scope, self.receive, self.send)

    async def test_denied_request_does_not_read_body_or_call_handler(self) -> None:
        self.limiter.check.return_value = RateLimitDecision(False, 12)
        await self.middleware(self.scope, self.receive, self.send)
        self.app.assert_not_awaited()
        self.receive.assert_not_awaited()
        start = self.send.await_args_list[0].args[0]
        self.assertEqual(start["status"], 429)
        self.assertIn((b"retry-after", b"12"), start["headers"])

    async def test_background_routes_consume_both_limits(self) -> None:
        for path in BACKGROUND_PATHS:
            with self.subTest(path=path):
                self.limiter.check.reset_mock()
                self.scope["path"] = path + "/"
                await self.middleware(self.scope, self.receive, self.send)
                self.limiter.check.assert_awaited_once_with(
                    "127.0.0.1", [RateLimit("writes", 60), RateLimit("background", 10)]
                )

    async def test_reads_health_and_non_http_bypass_redis(self) -> None:
        for change in (
            {"method": "GET"},
            {"path": "/health"},
            {"path": "/api/v10/batches"},
            {"type": "lifespan"},
        ):
            with self.subTest(change=change):
                await self.middleware(self.scope | change, self.receive, self.send)
        self.limiter.check.assert_not_awaited()
        self.assertEqual(self.app.await_count, 4)

    async def test_disabled_limiter_bypasses_redis(self) -> None:
        middleware = RateLimitMiddleware(self.app, self.limiter, enabled=False)
        await middleware(self.scope, self.receive, self.send)
        self.limiter.check.assert_not_awaited()
        self.app.assert_awaited_once()

    async def test_redis_outage_returns_503_before_body_processing(self) -> None:
        self.limiter.check.side_effect = ConnectionError("unavailable")
        await self.middleware(self.scope, self.receive, self.send)
        self.assertEqual(self.send.await_args_list[0].args[0]["status"], 503)
        self.app.assert_not_awaited()
        self.receive.assert_not_awaited()
