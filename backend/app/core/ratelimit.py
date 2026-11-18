import asyncio
import time

from redis import asyncio as aioredis

from app.core.config import settings
from app.core.exceptions import AppError

_local_hits: dict[str, list[float]] = {}
_local_lock = asyncio.Lock()


class RateLimitError(AppError):
    status_code = 429
    code = "rate_limited"


async def check_rate_limit(key: str, limit: int | None = None) -> None:
    limit = limit or settings.AUTH_RATE_LIMIT_PER_MINUTE
    try:
        redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            pipe = redis.pipeline()
            pipe.incr(key)
            pipe.expire(key, 60)
            count, _ = await pipe.execute()
            if int(count) > limit:
                raise RateLimitError("Too many attempts. Please try again later.")
            return
        finally:
            await redis.aclose()
    except RateLimitError:
        raise
    except Exception:
        pass

    now = time.monotonic()
    async with _local_lock:
        hits = [stamp for stamp in _local_hits.get(key, []) if now - stamp < 60]
        if len(hits) >= limit:
            raise RateLimitError("Too many attempts. Please try again later.")
        hits.append(now)
        _local_hits[key] = hits
