"""Cache control calculator service.

Calculates the overall cache policy for a GraphQL response by walking
the response data and aggregating cache hints from schema directives
and resolver-level hints.

Follows Apollo Server's cache control semantics:
- maxAge: Use the LOWEST value across all fields
- scope: Use PRIVATE if ANY field specifies PRIVATE
"""

from dataclasses import dataclass, field
from typing import Any

from cacheql.core.entities.cache_control import (
    CacheHint,
    CacheScope,
    FieldCacheHint,
    ResponseCachePolicy,
)
from cacheql.core.services.directive_parser import SchemaDirectives


@dataclass
class CacheControlContext:
    """Context for cache control during request execution.

    This context is passed through resolvers to collect cache hints
    and allow dynamic cache control from resolver code.
    """

    # Schema-level directives
    schema_directives: SchemaDirectives = field(default_factory=SchemaDirectives)

    # Hints set dynamically by resolvers
    resolver_hints: list[FieldCacheHint] = field(default_factory=list)

    # Default max_age for fields without explicit hints
    default_max_age: int = 0

    # Current field path during execution
    _current_path: list[str] = field(default_factory=list)

    def set_cache_hint(
        self,
        max_age: int | None = None,
        scope: CacheScope | str | None = None,
    ) -> None:
        """Set a cache hint for the current field (called from resolvers).

        This is the equivalent of Apollo's cacheControl.setCacheHint().

        Args:
            max_age: Maximum cache age in seconds.
            scope: Cache scope (PUBLIC, PRIVATE, or string).
        """
        parsed_scope = None
        if scope is not None:
            if isinstance(scope, str):
                parsed_scope = CacheScope(scope.upper())
            else:
                parsed_scope = scope

        hint = CacheHint(max_age=max_age, scope=parsed_scope)
        field_hint = FieldCacheHint(
            path=tuple(self._current_path),
            hint=hint,
            source="resolver",
        )
        self.resolver_hints.append(field_hint)

    def push_path(self, field_name: str) -> None:
        """Push a field name onto the current path."""
        self._current_path.append(field_name)

    def pop_path(self) -> None:
        """Pop the last field name from the current path."""
        if self._current_path:
            self._current_path.pop()

    @property
    def current_path(self) -> tuple[str, ...]:
        """Get the current field path as a tuple."""
        return tuple(self._current_path)


class CacheControlCalculator:
    """Calculates cache policy for GraphQL responses.

    Walks the response data and schema to collect all applicable
    cache hints, then calculates the overall policy using the
    most restrictive rules.
    """

    def __init__(
        self,
        schema_directives: SchemaDirectives | None = None,
        default_max_age: int = 0,
    ) -> None:
        """Initialize the calculator.

        Args:
            schema_directives: Pre-parsed schema directives.
            default_max_age: Default maxAge for fields without hints.
        """
        self._schema_directives = schema_directives or SchemaDirectives()
        self._default_max_age = default_max_age

    def calculate_policy(
        self,
        data: Any,
        type_info: dict[str, str] | None = None,
        context: CacheControlContext | None = None,
    ) -> ResponseCachePolicy:
        """Calculate the cache policy for a response.

        Args:
            data: The GraphQL response data.
            type_info: Optional mapping of field paths to type names.
            context: Optional cache control context with resolver hints.

        Returns:
            The calculated ResponseCachePolicy.
        """
        hints: list[FieldCacheHint] = []

        # Collect hints from schema directives by walking the response
        self._collect_hints_from_data(
            data=data,
            path=[],
            parent_type="Query",
            parent_hint=None,
            hints=hints,
            type_info=type_info or {},
        )

        # Add resolver hints from context
        if context is not None:
            hints.extend(context.resolver_hints)

        # Calculate overall policy
        return ResponseCachePolicy.from_hints(hints, self._default_max_age)

    def _collect_hints_from_data(
        self,
        data: Any,
        path: list[str],
        parent_type: str,
        parent_hint: CacheHint | None,
        hints: list[FieldCacheHint],
        type_info: dict[str, str],
    ) -> None:
        """Recursively collect cache hints from response data.

        Args:
            data: Current data node.
            path: Current field path.
            parent_type: The parent GraphQL type name.
            parent_hint: The parent field's cache hint.
            hints: List to append hints to.
            type_info: Mapping of paths to type names.
        """
        if data is None:
            return

        if isinstance(data, dict):
            # Get type from __typename or type_info
            type_name = data.get("__typename")
            if type_name is None:
                path_str = ".".join(path)
                type_name = type_info.get(path_str, parent_type)

            # Check for type-level hint
            type_hint = self._schema_directives.get_hint_for_type(type_name)
            if type_hint is not None:
                hints.append(FieldCacheHint(
                    path=tuple(path) if path else ("$root",),
                    hint=type_hint,
                    source="type",
                ))

            # Process each field
            for field_name, field_value in data.items():
                if field_name == "__typename":
                    continue

                field_path = [*path, field_name]

                # Get field-level hint
                field_hint = self._schema_directives.get_hint_for_field(
                    type_name=type_name or parent_type,
                    field_name=field_name,
                    parent_hint=parent_hint,
                )

                if field_hint is not None:
                    hints.append(FieldCacheHint(
                        path=tuple(field_path),
                        hint=field_hint,
                        source="schema",
                    ))

                # Recurse into nested data
                self._collect_hints_from_data(
                    data=field_value,
                    path=field_path,
                    parent_type=type_name or parent_type,
                    parent_hint=field_hint,
                    hints=hints,
                    type_info=type_info,
                )

        elif isinstance(data, list):
            # Process list items
            for item in data:
                self._collect_hints_from_data(
                    data=item,
                    path=path,  # Keep same path for list items
                    parent_type=parent_type,
                    parent_hint=parent_hint,
                    hints=hints,
                    type_info=type_info,
                )

    def calculate_from_hints(
        self,
        hints: list[FieldCacheHint],
    ) -> ResponseCachePolicy:
        """Calculate policy from a list of hints directly.

        Args:
            hints: List of field cache hints.

        Returns:
            The calculated ResponseCachePolicy.
        """
        return ResponseCachePolicy.from_hints(hints, self._default_max_age)


def create_cache_control_context(
    schema_directives: SchemaDirectives | None = None,
    default_max_age: int = 0,
) -> CacheControlContext:
    """Create a cache control context for request execution.

    This context should be added to the GraphQL context and passed
    to resolvers for dynamic cache control.

    Args:
        schema_directives: Pre-parsed schema directives.
        default_max_age: Default maxAge for fields.

    Returns:
        A new CacheControlContext.
    """
    return CacheControlContext(
        schema_directives=schema_directives or SchemaDirectives(),
        default_max_age=default_max_age,
    )
