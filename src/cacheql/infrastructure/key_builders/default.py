"""Default key builder implementation."""

from typing import Any

from cacheql.utils.hashing import hash_value, normalize_query


class DefaultKeyBuilder:
    """Default key builder using hash of query and variables.

    Creates deterministic cache keys from GraphQL operation parameters
    using SHA-256 hashing.
    """

    def __init__(
        self,
        prefix: str = "cacheql",
        include_operation_name: bool = True,
    ) -> None:
        """Initialize the key builder.

        Args:
            prefix: Prefix for all cache keys.
            include_operation_name: Whether to include operation name in key.
        """
        self._prefix = prefix
        self._include_operation_name = include_operation_name

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
            context: Optional additional context for key generation.

        Returns:
            A unique string key for caching the operation result.
        """
        parts = [self._prefix]

        # Add operation name if available and configured
        if self._include_operation_name and operation_name:
            parts.append(operation_name)

        # Hash normalized query
        normalized = normalize_query(query)
        query_hash = hash_value(normalized)
        parts.append(f"q:{query_hash}")

        # Hash variables
        if variables:
            vars_hash = hash_value(variables)
            parts.append(f"v:{vars_hash}")

        # Hash context if provided
        if context:
            ctx_hash = hash_value(context)
            parts.append(f"c:{ctx_hash}")

        return ":".join(parts)

    def build_field_key(
        self,
        type_name: str,
        field_name: str,
        args: dict[str, Any] | None = None,
        parent_value: Any | None = None,
    ) -> str:
        """Build cache key for field-level caching.

        Args:
            type_name: The GraphQL type name.
            field_name: The field name being resolved.
            args: Arguments passed to the field.
            parent_value: The parent/root value (for identification).

        Returns:
            A unique string key for caching the field result.
        """
        parts = [self._prefix, "field", type_name, field_name]

        if args:
            args_hash = hash_value(args)
            parts.append(f"a:{args_hash}")

        if parent_value is not None:
            # Try to get an ID or hash the value
            if hasattr(parent_value, "id"):
                parts.append(f"p:{parent_value.id}")
            elif isinstance(parent_value, dict) and "id" in parent_value:
                parts.append(f"p:{parent_value['id']}")
            else:
                parent_hash = hash_value(parent_value)
                parts.append(f"p:{parent_hash}")

        return ":".join(parts)
