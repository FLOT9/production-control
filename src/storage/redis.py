from redis.asyncio import Redis

from src.core.config import settings


def create_redis_client() -> Redis:
    return Redis.from_url(
        settings.redis_cache_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=1,
    )


redis_client = create_redis_client()


async def close_redis() -> None:
    await redis_client.aclose()
