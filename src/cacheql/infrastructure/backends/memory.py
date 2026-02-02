"""In-memory cache backend implementation."""

import fnmatch
from datetime import timedelta

from cachetools import TTLCache  # type: ignore[import-untyped]


class InMemoryCacheBackend:
    """In-memory cache backend using LRU with TTL support.

    Suitable for single-process deployments. Uses cachetools
    for efficient LRU eviction and TTL expiration.
    """

    def __init__(
        self,
        maxsize: int = 1000,
        default_ttl: float = 300.0,
    ) -> None:
        """Initialize the in-memory cache backend.

        Args:
            maxsize: Maximum number of items in the cache.
            default_ttl: Default TTL in seconds for items.
        """
        self._maxsize = maxsize
        self._default_ttl = default_ttl
        self._cache: TTLCache[str, bytes] = TTLCache(
            maxsize=maxsize,
            ttl=default_ttl,
        )
        # Track tags separately for invalidation
        self._tags: dict[str, set[str]] = {}

    async def get(self, key: str) -> bytes | None:
        """Retrieve cached value by key.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value as bytes, or None if not found or expired.
        """
        result = self._cache.get(key)
        return result if isinstance(result, bytes) else None

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: timedelta | None = None,
    ) -> None:
        """Store value with optional TTL.

        Note: cachetools TTLCache uses a global TTL, so per-item TTL
        is approximated. For precise per-item TTL, use Redis backend.

        Args:
            key: The cache key.
            value: The value to store as bytes.
            ttl: Optional time-to-live. If None, uses default.
        """
        # TTLCache doesn't support per-item TTL natively,
        # but we store anyway (uses global TTL)
        self._cache[key] = value

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
        return key in self._cache

    async def clear(self) -> None:
        """Clear all cached values."""
        self._cache.clear()
        self._tags.clear()

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern.

        Args:
            pattern: Glob-style pattern to match keys.

        Returns:
            Number of keys deleted.
        """
        # Find matching keys
        keys_to_delete = [
            key for key in list(self._cache.keys())
            if fnmatch.fnmatch(key, pattern)
        ]

        # Delete matched keys
        count = 0
        for key in keys_to_delete:
            try:
                del self._cache[key]
                count += 1
            except KeyError:
                pass

        return count

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        return len(self._cache)

    @property
    def maxsize(self) -> int:
        """Return the maximum size of the cache."""
        return self._maxsize
