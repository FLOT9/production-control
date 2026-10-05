from uuid import uuid4

from redis.asyncio import Redis


async def read_generation(
    client: Redis, key: str, ttl_seconds: int, *, create: bool = True
) -> str | None:
    """Capture a generation before SQL; expiry must never reuse an old token."""
    generation = await client.get(key)
    if generation is None and create:
        await client.set(key, uuid4().hex, nx=True, ex=ttl_seconds * 2)
        generation = await client.get(key)
    if generation is not None:
        # Repair legacy persistent keys without extending TTL on repeated reads.
        # NX also prevents a concurrent invalidation's fresh TTL from being changed.
        await client.expire(key, ttl_seconds * 2, nx=True)
    return generation
