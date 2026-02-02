"""Cache service - main orchestrator for caching operations."""

from datetime import timedelta
from typing import Any

from cacheql.core.entities.cache_config import CacheConfig
from cacheql.core.entities.cache_entry import CacheEntry
from cacheql.core.interfaces.cache_backend import ICacheBackend
from cacheql.core.interfaces.key_builder import IKeyBuilder
from cacheql.core.interfaces.serializer import ISerializer


class CacheService:
    """Domain service that orchestrates caching operations.

    This is the main entry point for cache operations,
    composing backend, key builder, and serializer.
    """

    def __init__(
        self,
        backend: ICacheBackend,
        key_builder: IKeyBuilder,
        serializer: ISerializer,
        config: CacheConfig | None = None,
    ) -> None:
        """Initialize the cache service.

        Args:
            backend: The cache backend to use for storage.
            key_builder: The key builder for generating cache keys.
            serializer: The serializer for encoding/decoding values.
            config: Optional cache configuration. Uses defaults if not provided.
        """
        self._backend = backend
        self._key_builder = key_builder
        self._serializer = serializer
        self._config = config or CacheConfig()

        # Statistics
        self._hits = 0
        self._misses = 0

    @property
    def config(self) -> CacheConfig:
        """Get the cache configuration."""
        return self._config

    @property
    def stats(self) -> dict[str, int]:
        """Get cache statistics.

        Returns:
            Dictionary with hits, misses, and total requests.
        """
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": self._hits + self._misses,
        }

    async def get_cached_response(
        self,
        operation_name: str | None,
        query: str,
        variables: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
    ) -> Any | None:
        """Try to get cached response for GraphQL operation.

        Args:
            operation_name: The GraphQL operation name.
            query: The GraphQL query string.
            variables: Variables passed to the operation.
            context: Optional additional context for key generation.

        Returns:
            The cached response value, or None if not found.
        """
        if not self._config.enabled:
            return None

        key = self._key_builder.build(
            operation_name=operation_name,
            query=query,
            variables=variables,
            context=context,
        )

        cached_data = await self._backend.get(key)

        if cached_data is None:
            self._misses += 1
            return None

        self._hits += 1
        return self._serializer.deserialize(cached_data)

    async def cache_response(
        self,
        operation_name: str | None,
        query: str,
        variables: dict[str, Any] | None,
        response: Any,
        ttl: timedelta | None = None,
        tags: list[str] | None = None,
        context: dict[str, Any] | None = None,
    ) -> CacheEntry:
        """Cache GraphQL response.

        Args:
            operation_name: The GraphQL operation name.
            query: The GraphQL query string.
            variables: Variables passed to the operation.
            response: The response to cache.
            ttl: Optional TTL. Uses config default if not provided.
            tags: Optional tags for invalidation.
            context: Optional additional context for key generation.

        Returns:
            The created CacheEntry.
        """
        if not self._config.enabled:
            return CacheEntry.create(
                key="",
                value=response,
                ttl=ttl or self._config.default_ttl,
                tags=tags,
            )

        key = self._key_builder.build(
            operation_name=operation_name,
            query=query,
            variables=variables,
            context=context,
        )

        effective_ttl = ttl or self._config.default_ttl

        # Create cache entry
        entry = CacheEntry.create(
            key=key,
            value=response,
            ttl=effective_ttl,
            tags=tags,
        )

        # Serialize and store
        serialized = self._serializer.serialize(response)
        await self._backend.set(key, serialized, effective_ttl)

        # Store tag mappings for invalidation
        if tags:
            await self._store_tag_mappings(key, tags)

        return entry

    async def invalidate(self, tags: list[str]) -> int:
        """Invalidate cached entries by tags.

        Args:
            tags: List of tags to invalidate.

        Returns:
            Number of entries invalidated.
        """
        count = 0
        for tag in tags:
            # Delete tag index and get associated keys
            pattern = f"{self._config.key_prefix}:tag:{tag}:*"
            count += await self._backend.delete_pattern(pattern)

            # Also try direct pattern matching
            pattern = f"{self._config.key_prefix}:*{tag}*"
            count += await self._backend.delete_pattern(pattern)

        return count

    async def invalidate_by_type(self, type_name: str) -> int:
        """Invalidate cached entries by GraphQL type.

        Args:
            type_name: The GraphQL type name to invalidate.

        Returns:
            Number of entries invalidated.
        """
        return await self.invalidate([type_name])

    async def clear(self) -> None:
        """Clear all cached entries."""
        await self._backend.clear()
        self._hits = 0
        self._misses = 0

    async def _store_tag_mappings(self, key: str, tags: list[str]) -> None:
        """Store mappings from tags to cache keys.

        Args:
            key: The cache key.
            tags: Tags to associate with the key.
        """
        for tag in tags:
            tag_key = f"{self._config.key_prefix}:tag:{tag}:{key}"
            # Store with same TTL as the main entry
            await self._backend.set(tag_key, key.encode(), self._config.default_ttl)
