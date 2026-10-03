"""Run once after deployment: poetry run python -m scripts.expire_cache_generations."""

import asyncio

from redis.asyncio import Redis

from src.core.config import settings
from src.storage.redis import create_redis_client


async def expire_legacy_generations(client: Redis, patterns: dict[str, int]) -> int:
    changed = 0
    for pattern, ttl in patterns.items():
        async for key in client.scan_iter(match=pattern, count=200):
            # Preserve tokens and existing expirations, including concurrent rotations.
            changed += int(await client.expire(key, ttl * 2, nx=True))
    return changed


async def main() -> None:
    client = create_redis_client()
    try:
        changed = await expire_legacy_generations(
            client,
            {
                "batch-details:v*:*:generation": settings.batch_details_cache_ttl_seconds,
                "work-center:v*:*:generation": settings.work_center_cache_ttl_seconds,
                "batch-statistics:v*:*:generation": settings.batch_statistics_cache_ttl_seconds,
                "batch-list:version": settings.batch_list_cache_ttl_seconds,
                "dashboard-summary:version": settings.dashboard_cache_ttl_seconds,
            },
        )
        print(f"Added TTL to {changed} persistent cache generation keys")
    finally:
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
