"""Key builder interface."""

from typing import Any, Protocol


class IKeyBuilder(Protocol):
    """Contract for building cache keys from GraphQL context.

    Key builders are responsible for creating unique, deterministic
    cache keys from GraphQL operation parameters.
    """

    def build(
        self,
        operation_name: str | None,
        query: str,
        variables: dict[str, Any] | None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Build unique cache key for a GraphQL operation.

        Args:
            operation_name: Name of the GraphQL operation (may be None).
            query: The GraphQL query string.
            variables: Variables passed to the operation.
            context: Optional additional context for key generation
                (e.g., user ID for user-specific caching).

        Returns:
            A unique string key for caching the operation result.
        """
        ...
