"""Redis cache backend implementation."""

from datetime import timedelta
from typing import Optional

import redis.asyncio as redis


class RedisCacheBackend:
    """Redis cache backend for distributed deployments.

    Supports TTL, pattern deletion, and is suitable for
    multi-process and distributed deployments.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        key_prefix: str = "cacheql",
        default_ttl: Optional[int] = 300,
    ) -> None:
        """Initialize the Redis cache backend.

        Args:
            redis_url: Redis connection URL.
            key_prefix: Prefix for all cache keys.
            default_ttl: Default TTL in seconds.
        """
        self._redis: redis.Redis = redis.from_url(redis_url)  # type: ignore
        self._key_prefix = key_prefix
        self._default_ttl = default_ttl

    async def get(self, key: str) -> Optional[bytes]:
        """Retrieve cached value by key.

        Args:
            key: The cache key to retrieve.

        Returns:
            The cached value as bytes, or None if not found or expired.
        """
        return await self._redis.get(self._prefixed_key(key))

    async def set(
        self,
        key: str,
        value: bytes,
        ttl: Optional[timedelta] = None,
    ) -> None:
        """Store value with optional TTL.

        Args:
            key: The cache key.
            value: The value to store as bytes.
            ttl: Optional time-to-live. If None, uses default.
        """
        prefixed_key = self._prefixed_key(key)

        if ttl is not None:
            await self._redis.setex(prefixed_key, int(ttl.total_seconds()), value)
        elif self._default_ttl is not None:
            await self._redis.setex(prefixed_key, self._default_ttl, value)
        else:
            await self._redis.set(prefixed_key, value)

    async def delete(self, key: str) -> bool:
        """Delete cached value.

        Args:
            key: The cache key to delete.

        Returns:
            True if the key existed and was deleted, False otherwise.
        """
        result = await self._redis.delete(self._prefixed_key(key))
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: The cache key to check.

        Returns:
            True if the key exists, False otherwise.
        """
        result = await self._redis.exists(self._prefixed_key(key))
        return result > 0

    async def clear(self) -> None:
        """Clear all cached values with our prefix.

        Note: This only clears keys with our prefix, not the entire Redis DB.
        """
        pattern = f"{self._key_prefix}:*"
        await self._delete_by_pattern(pattern)

    async def delete_pattern(self, pattern: str) -> int:
        """Delete keys matching pattern.

        Args:
            pattern: Glob-style pattern to match keys.

        Returns:
            Number of keys deleted.
        """
        return await self._delete_by_pattern(pattern)

    async def _delete_by_pattern(self, pattern: str) -> int:
        """Delete keys matching a pattern using SCAN.

        Uses SCAN instead of KEYS for production safety.

        Args:
            pattern: Redis glob pattern.

        Returns:
            Number of keys deleted.
        """
        count = 0
        cursor = 0

        while True:
            cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)

            if keys:
                deleted = await self._redis.delete(*keys)
                count += deleted

            if cursor == 0:
                break

        return count

    def _prefixed_key(self, key: str) -> str:
        """Add prefix to key if not already present.

        Args:
            key: The cache key.

        Returns:
            The key with prefix.
        """
        if key.startswith(f"{self._key_prefix}:"):
            return key
        return f"{self._key_prefix}:{key}"

    async def close(self) -> None:
        """Close the Redis connection."""
        await self._redis.close()

    async def __aenter__(self) -> "RedisCacheBackend":
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type: type, exc_val: Exception, exc_tb: object) -> None:
        """Async context manager exit."""
        await self.close()
