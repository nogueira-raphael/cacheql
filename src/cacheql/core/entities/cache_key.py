"""Cache key value object."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CacheKey:
    """Immutable cache key value object.

    Encapsulates all components that make up a cache key,
    providing a structured representation before hashing.
    """

    prefix: str
    operation_name: str | None
    query_hash: str
    variables_hash: str
    context_hash: str | None = None

    def __str__(self) -> str:
        """Return the full cache key string.

        Returns:
            The complete cache key as a string.
        """
        parts = [self.prefix]
        if self.operation_name:
            parts.append(self.operation_name)
        parts.extend([self.query_hash, self.variables_hash])
        if self.context_hash:
            parts.append(self.context_hash)
        return ":".join(parts)

    @classmethod
    def from_components(
        cls,
        prefix: str,
        operation_name: str | None,
        query: str,
        variables: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
        hash_func: Callable[[Any], str] | None = None,
    ) -> "CacheKey":
        """Create a CacheKey from raw components.

        Args:
            prefix: Cache key prefix.
            operation_name: GraphQL operation name.
            query: The GraphQL query string.
            variables: Query variables.
            context: Additional context for key generation.
            hash_func: Optional custom hash function.

        Returns:
            A new CacheKey instance.
        """
        from cacheql.utils.hashing import hash_value

        hasher = hash_func or hash_value

        return cls(
            prefix=prefix,
            operation_name=operation_name,
            query_hash=hasher(query),
            variables_hash=hasher(variables) if variables else "none",
            context_hash=hasher(context) if context else None,
        )
