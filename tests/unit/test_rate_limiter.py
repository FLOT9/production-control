from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock

from redis.exceptions import ConnectionError

from src.storage.rate_limiter import CHECK_AND_INCREMENT, RateLimit, RedisRateLimiter


class RateLimiterTests(IsolatedAsyncioTestCase):
    async def test_checks_both_groups_in_one_redis_call(self) -> None:
        client = AsyncMock()
        client.eval.return_value = 0
        limiter = RedisRateLimiter(client)

        decision = await limiter.check(
            "127.0.0.1", [RateLimit("writes", 60), RateLimit("background", 10)]
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.retry_after_seconds, 0)
        client.eval.assert_awaited_once_with(
            CHECK_AND_INCREMENT,
            2,
            "rate-limit:v1:writes:127.0.0.1",
            "rate-limit:v1:background:127.0.0.1",
            "60000",
            "60",
            "10",
        )

    async def test_rounds_retry_up_to_whole_seconds(self) -> None:
        client = AsyncMock()
        client.eval.return_value = 1001

        decision = await RedisRateLimiter(client).check("::1", [RateLimit("writes", 2)])

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.retry_after_seconds, 2)

    async def test_redis_failure_is_not_treated_as_permission(self) -> None:
        client = AsyncMock()
        client.eval.side_effect = ConnectionError("Redis unavailable")

        with self.assertRaises(ConnectionError):
            await RedisRateLimiter(client).check("::1", [RateLimit("writes", 2)])

    async def test_no_limits_does_not_access_redis(self) -> None:
        client = AsyncMock()
        decision = await RedisRateLimiter(client).check("::1", [])
        self.assertTrue(decision.allowed)
        client.eval.assert_not_awaited()

    async def test_rejects_invalid_configuration_before_redis(self) -> None:
        client = AsyncMock()
        with self.assertRaises(ValueError):
            RedisRateLimiter(client, window_seconds=0)
        limiter = RedisRateLimiter(client)
        for limits in (
            [RateLimit("writes", 0)],
            [RateLimit("", 1)],
            [RateLimit("writes", 1), RateLimit("writes", 2)],
        ):
            with self.subTest(limits=limits), self.assertRaises(ValueError):
                await limiter.check("::1", limits)
        client.eval.assert_not_awaited()
