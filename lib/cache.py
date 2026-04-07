"""Simple in-memory TTL cache for expensive external API calls."""

import threading
import time
from typing import Any, Callable

_store: dict[str, tuple[Any, float]] = {}
_locks: dict[str, threading.Lock] = {}
_meta_lock = threading.Lock()


def _get_lock(key: str) -> threading.Lock:
    with _meta_lock:
        if key not in _locks:
            _locks[key] = threading.Lock()
        return _locks[key]


def ttl_cache(ttl_seconds: int, key: str):
    """Decorator: cache the result in memory for ttl_seconds.

    Uses a per-key lock to prevent cache stampedes — only one thread
    will call the underlying function on a cold cache; others wait for it.
    """

    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            now = time.time()
            cached = _store.get(key)
            if cached and now < cached[1]:
                return cached[0]

            with _get_lock(key):
                # Re-check inside the lock — another thread may have just populated it
                cached = _store.get(key)
                if cached and now < cached[1]:
                    return cached[0]
                result = func(*args, **kwargs)
                _store[key] = (result, time.time() + ttl_seconds)
                return result

        return wrapper

    return decorator


def invalidate(key: str) -> None:
    """Remove a cached entry (e.g. after a roster update)."""
    _store.pop(key, None)
