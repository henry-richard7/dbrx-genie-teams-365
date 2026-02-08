"""
Utility decorators for the Databricks Genie Bot.
"""

import time
from functools import wraps


def sync_lru_cache_async(maxsize=128):
    """Simpler async cache - caches the result after first call."""

    def decorator(func):
        cache = {}
        cache_time = {}
        ttl = 300  # 5 minutes

        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create cache key
            key = str(args) + str(sorted(kwargs.items()))
            current_time = time.time()

            # Check if we have valid cached result
            if key in cache and current_time - cache_time.get(key, 0) < ttl:
                return cache[key]

            # Get fresh result
            result = await func(*args, **kwargs)

            # Cache it
            cache[key] = result
            cache_time[key] = current_time

            # Simple cleanup - keep only maxsize items
            if len(cache) > maxsize:
                oldest_key = min(cache_time.keys(), key=lambda k: cache_time[k])
                del cache[oldest_key]
                del cache_time[oldest_key]

            return result

        wrapper.cache_clear = lambda: (cache.clear(), cache_time.clear())
        return wrapper

    return decorator
