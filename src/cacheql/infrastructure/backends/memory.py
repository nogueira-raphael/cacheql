"""In-memory cache backend implementation."""

import fnmatch
import time
from datetime import timedelta

from cachetools import LRUCache

# (serialized value, absolute expiry time in monotonic seconds, or None
# for "never expires")
_Entry = tuple[bytes, float | None]


class InMemoryCacheBackend:
    """In-memory cache backend using LRU eviction with per-item TTL.

    Suitable for single-process deployments. Uses cachetools' LRUCache
    for maxsize eviction, with expiry tracked and enforced per entry so
    that different cache-control maxAge values are actually honored.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        default_ttl: float = 300.0,
    ) -> None:
        """Initialize the in-memory cache backend.

        Args:
            maxsize: Maximum number of items in the cache.
            default_ttl: Default TTL in seconds, used when ``set()`` is
                called without an explicit ``ttl``.
        """
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._cache: LRUCache[str, _Entry] = LRUCache(maxsize=maxsize)

    def _is_expired(self, expire_at: float | None) -> bool:
        return expire_at is not None and expire_at <= time.monotonic()

    async def get(self, key: str) -> bytes | None:
        """Retrieve cached value by key.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value as bytes, or None if not found or expired.
        """
        entry = self._cache.get(key)
        if entry is None:
            return None

        value: bytes
        expire_at: float | None
        value, expire_at = entry
        if self._is_expired(expire_at):
            self._cache.pop(key, None)
            return None

        return value

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: timedelta | None = None,
    ) -> None:
        """Store value with optional per-item TTL.

        Args:
            key: The cache key.
            value: The value to store as bytes.
            ttl: Optional time-to-live. If None, uses ``default_ttl``.
        """
        effective_ttl = ttl.total_seconds() if ttl is not None else self._default_ttl
        expire_at = (
            time.monotonic() + effective_ttl if effective_ttl is not None else None
        )
        self._cache[key] = (value, expire_at)

    async def delete(self, key: str) -> bool:
        """Delete cached value.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        try:
            del self._cache[key]
            return True
        except KeyError:
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        return await self.get(key) is not None

    async def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern.

        Args:
            pattern: Glob-style pattern to match keys.

        Returns:
            Number of keys deleted.
        """
        count = 0
        for key in await self.keys(pattern):
            if await self.delete(key):
                count += 1
        return count

    async def keys(self, pattern: str) -> list[str]:
        """List non-expired keys matching a glob pattern.

        Args:
            pattern: Glob-style pattern to match keys.

        Returns:
            Matching keys, with any expired entries purged along the way.
        """
        matched: list[str] = []
        for key, (_value, expire_at) in list(self._cache.items()):
            if self._is_expired(expire_at):
                self._cache.pop(key, None)
                continue
            if fnmatch.fnmatch(key, pattern):
                matched.append(key)
        return matched

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        return len(self._cache)

    @property
    def maxsize(self) -> int:
        """Return the maximum size of the cache."""
        return self._maxsize
