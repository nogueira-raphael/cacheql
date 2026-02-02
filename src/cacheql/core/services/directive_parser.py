"""Parser for @cacheControl directives in GraphQL schemas.

Extracts cache control settings from schema definitions following
Apollo Server's @cacheControl directive semantics.
"""

from dataclasses import dataclass, field
from typing import Any

from cacheql.core.entities.cache_control import CacheHint, CacheScope

# The @cacheControl directive definition to add to schemas
CACHE_CONTROL_DIRECTIVE = '''
"""Cache control directive for field and type caching configuration."""
directive @cacheControl(
  """Maximum cache age in seconds."""
  maxAge: Int
  """Cache scope: PUBLIC or PRIVATE."""
  scope: CacheControlScope
  """Inherit maxAge from parent field instead of using default."""
  inheritMaxAge: Boolean
) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION

"""Cache scope enum."""
enum CacheControlScope {
  """Response can be cached globally (CDN, shared cache)."""
  PUBLIC
  """Response contains user-specific data, cache per-user only."""
  PRIVATE
}
'''


@dataclass
class SchemaDirectives:
    """Extracted cache control directives from a schema.

    Stores both type-level and field-level cache hints.
    """

    # Type-level hints: type_name -> CacheHint
    type_hints: dict[str, CacheHint] = field(default_factory=dict)

    # Field-level hints: "TypeName.fieldName" -> CacheHint
    field_hints: dict[str, CacheHint] = field(default_factory=dict)

    def get_hint_for_field(
        self,
        type_name: str,
        field_name: str,
        parent_hint: CacheHint | None = None,
    ) -> CacheHint | None:
        """Get the cache hint for a specific field.

        Resolution order (first match wins):
        1. Field-level directive
        2. Type-level directive (on the field's return type)
        3. Parent hint (if inheritMaxAge is set)

        Args:
            type_name: The parent type name.
            field_name: The field name.
            parent_hint: The parent field's cache hint (for inheritance).

        Returns:
            The resolved CacheHint, or None if not set.
        """
        field_key = f"{type_name}.{field_name}"

        # Check field-level directive first
        if field_key in self.field_hints:
            hint = self.field_hints[field_key]
            if hint.inherit_max_age and parent_hint is not None:
                return CacheHint(
                    max_age=parent_hint.max_age,
                    scope=hint.scope or parent_hint.scope,
                    inherit_max_age=False,
                )
            return hint

        # Check type-level directive
        if type_name in self.type_hints:
            return self.type_hints[type_name]

        return None

    def get_hint_for_type(self, type_name: str) -> CacheHint | None:
        """Get the cache hint for a type.

        Args:
            type_name: The type name.

        Returns:
            The CacheHint for the type, or None if not set.
        """
        return self.type_hints.get(type_name)


class DirectiveParser:
    """Parser for extracting @cacheControl directives from GraphQL schemas."""

    def __init__(self, default_max_age: int = 0) -> None:
        """Initialize the directive parser.

        Args:
            default_max_age: Default maxAge for root fields (Query/Mutation).
        """
        self._default_max_age = default_max_age

    def parse_schema(self, schema: Any) -> SchemaDirectives:
        """Parse a GraphQL schema and extract cache control directives.

        Args:
            schema: The GraphQL schema object (graphql-core schema).

        Returns:
            SchemaDirectives containing all extracted hints.
        """
        directives = SchemaDirectives()

        # Try to import graphql-core types
        try:
            from graphql import GraphQLSchema
        except ImportError:
            # graphql-core not installed, return empty directives
            return directives

        if not isinstance(schema, GraphQLSchema):
            return directives

        # Parse type definitions
        for type_name, type_def in schema.type_map.items():
            # Skip built-in types
            if type_name.startswith("__"):
                continue

            # Extract type-level directive
            type_hint = self._extract_directive_from_node(type_def)
            if type_hint is not None:
                directives.type_hints[type_name] = type_hint

            # Extract field-level directives
            if hasattr(type_def, "fields"):
                fields = type_def.fields
                if callable(fields):
                    fields = fields()
                if isinstance(fields, dict):
                    for field_name, field_def in fields.items():
                        field_hint = self._extract_directive_from_node(field_def)
                        if field_hint is not None:
                            field_key = f"{type_name}.{field_name}"
                            directives.field_hints[field_key] = field_hint

        return directives

    def _extract_directive_from_node(self, node: Any) -> CacheHint | None:
        """Extract @cacheControl directive from a schema node.

        Args:
            node: A GraphQL type or field definition.

        Returns:
            CacheHint if directive is present, None otherwise.
        """
        # Check if node has AST node with directives
        ast_node = getattr(node, "ast_node", None)
        if ast_node is None:
            return None

        directives = getattr(ast_node, "directives", None)
        if not directives:
            return None

        # Find @cacheControl directive
        for directive in directives:
            name = getattr(directive.name, "value", None)
            if name == "cacheControl":
                return self._parse_cache_control_directive(directive)

        return None

    def _parse_cache_control_directive(self, directive: Any) -> CacheHint:
        """Parse a @cacheControl directive node.

        Args:
            directive: The directive AST node.

        Returns:
            The parsed CacheHint.
        """
        max_age: int | None = None
        scope: CacheScope | None = None
        inherit_max_age = False

        arguments = getattr(directive, "arguments", [])
        for arg in arguments:
            arg_name = getattr(arg.name, "value", None)
            arg_value = self._get_argument_value(arg.value)

            if arg_name == "maxAge" and isinstance(arg_value, int):
                max_age = arg_value
            elif arg_name == "scope" and isinstance(arg_value, str):
                scope = CacheScope(arg_value.upper())
            elif arg_name == "inheritMaxAge" and isinstance(arg_value, bool):
                inherit_max_age = arg_value

        return CacheHint(
            max_age=max_age,
            scope=scope,
            inherit_max_age=inherit_max_age,
        )

    def _get_argument_value(self, value_node: Any) -> Any:
        """Extract the value from an argument value node.

        Args:
            value_node: The AST value node.

        Returns:
            The Python value.
        """
        # Handle different AST node types
        node_kind = type(value_node).__name__

        if node_kind == "IntValueNode":
            return int(value_node.value)
        elif node_kind == "FloatValueNode":
            return float(value_node.value)
        elif node_kind in ("StringValueNode", "BooleanValueNode", "EnumValueNode"):
            return value_node.value
        elif node_kind == "NullValueNode":
            return None

        return None


def get_cache_control_directive_sdl() -> str:
    """Get the SDL definition for @cacheControl directive.

    Add this to your schema to enable cache control directives.

    Returns:
        The SDL string for the directive definition.
    """
    return CACHE_CONTROL_DIRECTIVE
