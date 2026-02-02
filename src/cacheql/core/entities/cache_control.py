"""Cache control entities following Apollo Server's model.

These entities implement the @cacheControl directive semantics from Apollo Server,
enabling per-field and per-type cache configuration in GraphQL schemas.

See: https://www.apollographql.com/docs/apollo-server/performance/caching
"""

from dataclasses import dataclass, field
from enum import Enum


class CacheScope(Enum):
    """Cache scope for cache control.

    PUBLIC: Response can be cached globally (CDN, shared cache).
    PRIVATE: Response contains user-specific data, only cache per-user.
    """

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"


@dataclass
class CacheHint:
    """Cache hint for a field or type.

    Represents the caching policy as defined by @cacheControl directive.
    Used to calculate the overall cache policy for a response.

    Attributes:
        max_age: Maximum cache validity in seconds. None means not set.
        scope: PUBLIC or PRIVATE scope. None means not set.
        inherit_max_age: If True, inherit maxAge from parent field.
    """

    max_age: int | None = None
    scope: CacheScope | None = None
    inherit_max_age: bool = False

    def is_set(self) -> bool:
        """Check if any cache hint value is set."""
        return self.max_age is not None or self.scope is not None

    def merge_with(self, other: "CacheHint") -> "CacheHint":
        """Merge this hint with another, applying most restrictive rules.

        Rules (following Apollo Server):
        - max_age: Use the LOWEST value (most restrictive)
        - scope: Use PRIVATE if either is PRIVATE

        Args:
            other: The other cache hint to merge with.

        Returns:
            A new CacheHint with merged values.
        """
        # Calculate max_age (lowest wins)
        if self.max_age is None:
            new_max_age = other.max_age
        elif other.max_age is None:
            new_max_age = self.max_age
        else:
            new_max_age = min(self.max_age, other.max_age)

        # Calculate scope (PRIVATE wins)
        new_scope: CacheScope | None
        if self.scope == CacheScope.PRIVATE or other.scope == CacheScope.PRIVATE:
            new_scope = CacheScope.PRIVATE
        elif self.scope is not None:
            new_scope = self.scope
        else:
            new_scope = other.scope

        return CacheHint(
            max_age=new_max_age,
            scope=new_scope,
            inherit_max_age=False,  # Not applicable after merge
        )

    def restrict(
        self,
        max_age: int | None = None,
        scope: CacheScope | None = None,
    ) -> "CacheHint":
        """Apply more restrictive settings to this hint.

        Args:
            max_age: New max_age to consider (uses min if set).
            scope: New scope to consider (PRIVATE wins).

        Returns:
            A new CacheHint with restricted values.
        """
        return self.merge_with(CacheHint(max_age=max_age, scope=scope))

    def to_http_header(self) -> str | None:
        """Generate HTTP Cache-Control header value.

        Returns:
            The Cache-Control header value, or None if not cacheable.
        """
        if self.max_age is None or self.max_age == 0:
            return "no-store"

        scope_str = "private" if self.scope == CacheScope.PRIVATE else "public"
        return f"max-age={self.max_age}, {scope_str}"

    @classmethod
    def no_cache(cls) -> "CacheHint":
        """Create a hint that disables caching."""
        return cls(max_age=0, scope=CacheScope.PUBLIC)

    @classmethod
    def from_directive(
        cls,
        max_age: int | None = None,
        scope: str | None = None,
        inherit_max_age: bool = False,
    ) -> "CacheHint":
        """Create a CacheHint from @cacheControl directive parameters.

        Args:
            max_age: The maxAge value from the directive.
            scope: The scope value ("PUBLIC" or "PRIVATE").
            inherit_max_age: The inheritMaxAge value from the directive.

        Returns:
            A new CacheHint instance.
        """
        parsed_scope = None
        if scope:
            parsed_scope = CacheScope(scope.upper())

        return cls(
            max_age=max_age,
            scope=parsed_scope,
            inherit_max_age=inherit_max_age,
        )


@dataclass
class FieldCacheHint:
    """Cache hint associated with a specific field path.

    Used to track cache hints from resolvers and schema directives
    during query execution.
    """

    path: tuple[str, ...]
    hint: CacheHint
    source: str = "schema"  # "schema", "resolver", or "type"

    @property
    def path_string(self) -> str:
        """Get the field path as a dot-separated string."""
        return ".".join(self.path)


@dataclass
class ResponseCachePolicy:
    """Overall cache policy for a GraphQL response.

    Calculated by aggregating all field hints using most restrictive rules.
    """

    max_age: int
    scope: CacheScope
    field_hints: list[FieldCacheHint] = field(default_factory=list)

    @property
    def is_cacheable(self) -> bool:
        """Check if the response is cacheable."""
        return self.max_age > 0

    def to_http_header(self) -> str:
        """Generate HTTP Cache-Control header value."""
        if not self.is_cacheable:
            return "no-store"

        scope_str = "private" if self.scope == CacheScope.PRIVATE else "public"
        return f"max-age={self.max_age}, {scope_str}"

    @classmethod
    def from_hints(
        cls,
        hints: list[FieldCacheHint],
        default_max_age: int = 0,
    ) -> "ResponseCachePolicy":
        """Calculate response cache policy from field hints.

        Applies Apollo Server's rules:
        - max_age: Use the LOWEST value across all fields
        - scope: Use PRIVATE if any field is PRIVATE

        Args:
            hints: List of field cache hints.
            default_max_age: Default max_age if no hints are set.

        Returns:
            The calculated ResponseCachePolicy.
        """
        if not hints:
            return cls(
                max_age=default_max_age,
                scope=CacheScope.PUBLIC,
                field_hints=[],
            )

        # Start with most permissive values
        overall_max_age: int | None = None
        overall_scope = CacheScope.PUBLIC

        for field_hint in hints:
            hint = field_hint.hint

            # Update max_age (lowest wins)
            if hint.max_age is not None:
                if overall_max_age is None:
                    overall_max_age = hint.max_age
                else:
                    overall_max_age = min(overall_max_age, hint.max_age)

            # Update scope (PRIVATE wins)
            if hint.scope == CacheScope.PRIVATE:
                overall_scope = CacheScope.PRIVATE

        return cls(
            max_age=overall_max_age if overall_max_age is not None else default_max_age,
            scope=overall_scope,
            field_hints=hints,
        )


# Type alias for cache control configuration per field/type
CacheControlConfig = dict[str, CacheHint]
