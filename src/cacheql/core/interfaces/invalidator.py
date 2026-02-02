"""Cache invalidator interface."""

from typing import Protocol

from cacheql.core.interfaces.cache_backend import ICacheBackend


class IInvalidator(Protocol):
    """Contract for cache invalidation strategies.

    Invalidators implement different strategies for clearing
    cached entries based on tags, types, or other criteria.
    """

    async def invalidate_by_tags(
        self,
        backend: ICacheBackend,
        tags: list[str],
    ) -> int:
        """Invalidate cache entries by tags.

        Args:
            backend: The cache backend to invalidate entries from.
            tags: List of tags to invalidate.

        Returns:
            Number of entries invalidated.
        """
        ...

    async def invalidate_by_type(
        self,
        backend: ICacheBackend,
        type_name: str,
    ) -> int:
        """Invalidate cache entries by GraphQL type.

        Args:
            backend: The cache backend to invalidate entries from.
            type_name: The GraphQL type name to invalidate.

        Returns:
            Number of entries invalidated.
        """
        ...
