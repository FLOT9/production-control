from collections.abc import Awaitable, Sequence
from dataclasses import dataclass
from typing import cast

from redis.asyncio import Redis

# Redis executes the whole script without interleaving other requests.
CHECK_AND_INCREMENT = """
local retry_ms = 0
for i, key in ipairs(KEYS) do
    local count = tonumber(redis.call('GET', key) or '0')
    if count >= tonumber(ARGV[i + 1]) then
        local ttl = redis.call('PTTL', key)
        if ttl < 0 then
            redis.call('PEXPIRE', key, ARGV[1])
            ttl = tonumber(ARGV[1])
        end
        retry_ms = math.max(retry_ms, ttl, 1)
    end
end
if retry_ms > 0 then
    return retry_ms
end
for _, key in ipairs(KEYS) do
    redis.call('INCR', key)
    if redis.call('PTTL', key) < 0 then
        redis.call('PEXPIRE', key, ARGV[1])
    end
end
return 0
"""


@dataclass(frozen=True, slots=True)
class RateLimit:
    group: str
    requests: int


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class RedisRateLimiter:
    def __init__(self, client: Redis, window_seconds: int = 60) -> None:
        if window_seconds <= 0:
            raise ValueError("Rate limit window must be positive")
        self.client = client
        self.window_seconds = window_seconds

    async def check(
        self, client_id: str, limits: Sequence[RateLimit]
    ) -> RateLimitDecision:
        if not limits:
            return RateLimitDecision(allowed=True, retry_after_seconds=0)
        if any(limit.requests <= 0 or not limit.group for limit in limits):
            raise ValueError("Rate limit groups and positive limits are required")
        if len({limit.group for limit in limits}) != len(limits):
            raise ValueError("Rate limit groups must be unique")

        keys = [f"rate-limit:v1:{limit.group}:{client_id}" for limit in limits]
        result = await cast(
            Awaitable[str],
            self.client.eval(
                CHECK_AND_INCREMENT,
                len(keys),
                *keys,
                str(self.window_seconds * 1000),
                *(str(limit.requests) for limit in limits),
            ),
        )
        retry_ms = int(result)
        return RateLimitDecision(
            allowed=retry_ms == 0,
            retry_after_seconds=(retry_ms + 999) // 1000,
        )
