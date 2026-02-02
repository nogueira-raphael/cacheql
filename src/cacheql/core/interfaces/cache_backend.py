"""Cache backend interface."""

from datetime import timedelta
from typing import Protocol


class ICacheBackend(Protocol):
    """Contract for cache storage backends.

    All cache backends must implement this protocol to be used
    with CacheService. Methods are async to support both in-memory
    and distributed cache implementations.
    """

    async def get(self, key: str) -> bytes | None:
        """Retrieve cached value by key.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value as bytes, or None if not found or expired.
        """
        ...

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: timedelta | None = None,
    ) -> None:
        """Store value with optional TTL.

        Args:
            key: The cache key.
            value: The value to store as bytes.
            ttl: Optional time-to-live. If None, uses backend default.
        """
        ...

    async def delete(self, key: str) -> bool:
        """Delete cached value.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        ...

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        ...

    async def clear(self) -> None:
        """Clear all cached values."""
        ...

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern.

        Args:
            pattern: Glob-style pattern to match keys.

        Returns:
            Number of keys deleted.
        """
        ...
