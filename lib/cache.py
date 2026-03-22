"""Simple in-memory TTL cache for expensive external API calls."""

import time
from typing import Any, Callable

_store: dict[str, tuple[Any, float]] = {}


def ttl_cache(ttl_seconds: int, key: str):
    """Decorator: cache the result in memory for ttl_seconds."""

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            now = time.time()
            if key in _store:
                value, expires = _store[key]
                if now < expires:
                    return value
            result = func(*args, **kwargs)
            _store[key] = (result, now + ttl_seconds)
            return result

        return wrapper

    return decorator


def invalidate(key: str) -> None:
    """Remove a cached entry (e.g. after a roster update)."""
    _store.pop(key, None)
