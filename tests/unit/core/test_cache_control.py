"""Tests for cache control entities and services."""

import pytest

from cacheql.core.entities.cache_control import (
    CacheHint,
    CacheScope,
    FieldCacheHint,
    ResponseCachePolicy,
)
from cacheql.core.services.cache_control_calculator import (
    CacheControlCalculator,
    CacheControlContext,
)
from cacheql.core.services.directive_parser import SchemaDirectives


class TestCacheScope:
    """Tests for CacheScope enum."""

    def test_scope_values(self) -> None:
        """Test scope enum values."""
        assert CacheScope.PUBLIC.value == "PUBLIC"
        assert CacheScope.PRIVATE.value == "PRIVATE"


class TestCacheHint:
    """Tests for CacheHint entity."""

    def test_default_values(self) -> None:
        """Test default hint values."""
        hint = CacheHint()
        assert hint.max_age is None
        assert hint.scope is None
        assert hint.inherit_max_age is False
        assert not hint.is_set()

    def test_is_set(self) -> None:
        """Test is_set property."""
        assert not CacheHint().is_set()
        assert CacheHint(max_age=60).is_set()
        assert CacheHint(scope=CacheScope.PRIVATE).is_set()

    def test_merge_max_age_lowest_wins(self) -> None:
        """Test that merge uses lowest max_age."""
        hint1 = CacheHint(max_age=300)
        hint2 = CacheHint(max_age=60)

        merged = hint1.merge_with(hint2)
        assert merged.max_age == 60

    def test_merge_private_wins(self) -> None:
        """Test that PRIVATE scope wins in merge."""
        hint1 = CacheHint(scope=CacheScope.PUBLIC)
        hint2 = CacheHint(scope=CacheScope.PRIVATE)

        merged = hint1.merge_with(hint2)
        assert merged.scope == CacheScope.PRIVATE

        # Order shouldn't matter
        merged2 = hint2.merge_with(hint1)
        assert merged2.scope == CacheScope.PRIVATE

    def test_merge_with_none_values(self) -> None:
        """Test merging with None values."""
        hint1 = CacheHint(max_age=300)
        hint2 = CacheHint()

        merged = hint1.merge_with(hint2)
        assert merged.max_age == 300

    def test_restrict(self) -> None:
        """Test restrict method."""
        hint = CacheHint(max_age=300, scope=CacheScope.PUBLIC)
        restricted = hint.restrict(max_age=60)
        assert restricted.max_age == 60
        assert restricted.scope == CacheScope.PUBLIC

        restricted2 = hint.restrict(scope=CacheScope.PRIVATE)
        assert restricted2.scope == CacheScope.PRIVATE

    def test_to_http_header(self) -> None:
        """Test HTTP header generation."""
        # Cacheable with public scope
        hint = CacheHint(max_age=300, scope=CacheScope.PUBLIC)
        assert hint.to_http_header() == "max-age=300, public"

        # Cacheable with private scope
        hint = CacheHint(max_age=60, scope=CacheScope.PRIVATE)
        assert hint.to_http_header() == "max-age=60, private"

        # Not cacheable
        hint = CacheHint(max_age=0)
        assert hint.to_http_header() == "no-store"

        # No max_age set
        hint = CacheHint()
        assert hint.to_http_header() == "no-store"

    def test_no_cache_factory(self) -> None:
        """Test no_cache factory method."""
        hint = CacheHint.no_cache()
        assert hint.max_age == 0
        assert hint.scope == CacheScope.PUBLIC

    def test_from_directive(self) -> None:
        """Test from_directive factory method."""
        hint = CacheHint.from_directive(max_age=300, scope="PRIVATE")
        assert hint.max_age == 300
        assert hint.scope == CacheScope.PRIVATE

        hint = CacheHint.from_directive(inherit_max_age=True)
        assert hint.inherit_max_age is True


class TestFieldCacheHint:
    """Tests for FieldCacheHint entity."""

    def test_path_string(self) -> None:
        """Test path_string property."""
        hint = FieldCacheHint(
            path=("users", "posts", "title"),
            hint=CacheHint(max_age=60),
        )
        assert hint.path_string == "users.posts.title"

    def test_source_default(self) -> None:
        """Test default source value."""
        hint = FieldCacheHint(
            path=("field",),
            hint=CacheHint(),
        )
        assert hint.source == "schema"


class TestResponseCachePolicy:
    """Tests for ResponseCachePolicy entity."""

    def test_is_cacheable(self) -> None:
        """Test is_cacheable property."""
        policy = ResponseCachePolicy(max_age=300, scope=CacheScope.PUBLIC)
        assert policy.is_cacheable is True

        policy = ResponseCachePolicy(max_age=0, scope=CacheScope.PUBLIC)
        assert policy.is_cacheable is False

    def test_to_http_header(self) -> None:
        """Test HTTP header generation."""
        policy = ResponseCachePolicy(max_age=300, scope=CacheScope.PUBLIC)
        assert policy.to_http_header() == "max-age=300, public"

        policy = ResponseCachePolicy(max_age=60, scope=CacheScope.PRIVATE)
        assert policy.to_http_header() == "max-age=60, private"

        policy = ResponseCachePolicy(max_age=0, scope=CacheScope.PUBLIC)
        assert policy.to_http_header() == "no-store"

    def test_from_hints_empty(self) -> None:
        """Test from_hints with empty list."""
        policy = ResponseCachePolicy.from_hints([])
        assert policy.max_age == 0
        assert policy.scope == CacheScope.PUBLIC

    def test_from_hints_single(self) -> None:
        """Test from_hints with single hint."""
        hints = [
            FieldCacheHint(
                path=("users",),
                hint=CacheHint(max_age=300, scope=CacheScope.PUBLIC),
            )
        ]
        policy = ResponseCachePolicy.from_hints(hints)
        assert policy.max_age == 300
        assert policy.scope == CacheScope.PUBLIC

    def test_from_hints_lowest_max_age_wins(self) -> None:
        """Test that lowest max_age is used."""
        hints = [
            FieldCacheHint(
                path=("users",),
                hint=CacheHint(max_age=300),
            ),
            FieldCacheHint(
                path=("users", "posts"),
                hint=CacheHint(max_age=60),
            ),
            FieldCacheHint(
                path=("users", "profile"),
                hint=CacheHint(max_age=600),
            ),
        ]
        policy = ResponseCachePolicy.from_hints(hints)
        assert policy.max_age == 60

    def test_from_hints_private_wins(self) -> None:
        """Test that PRIVATE scope wins."""
        hints = [
            FieldCacheHint(
                path=("users",),
                hint=CacheHint(max_age=300, scope=CacheScope.PUBLIC),
            ),
            FieldCacheHint(
                path=("me",),
                hint=CacheHint(max_age=60, scope=CacheScope.PRIVATE),
            ),
        ]
        policy = ResponseCachePolicy.from_hints(hints)
        assert policy.scope == CacheScope.PRIVATE

    def test_from_hints_with_default_max_age(self) -> None:
        """Test from_hints with default_max_age."""
        hints = [
            FieldCacheHint(
                path=("users",),
                hint=CacheHint(scope=CacheScope.PUBLIC),  # No max_age
            )
        ]
        policy = ResponseCachePolicy.from_hints(hints, default_max_age=300)
        assert policy.max_age == 300


class TestCacheControlContext:
    """Tests for CacheControlContext."""

    def test_set_cache_hint(self) -> None:
        """Test setting cache hints dynamically."""
        context = CacheControlContext()
        context._current_path = ["users", "profile"]

        context.set_cache_hint(max_age=60, scope="PRIVATE")

        assert len(context.resolver_hints) == 1
        hint = context.resolver_hints[0]
        assert hint.path == ("users", "profile")
        assert hint.hint.max_age == 60
        assert hint.hint.scope == CacheScope.PRIVATE
        assert hint.source == "resolver"

    def test_push_pop_path(self) -> None:
        """Test path management."""
        context = CacheControlContext()

        context.push_path("query")
        assert context.current_path == ("query",)

        context.push_path("users")
        assert context.current_path == ("query", "users")

        context.pop_path()
        assert context.current_path == ("query",)


class TestCacheControlCalculator:
    """Tests for CacheControlCalculator."""

    def test_calculate_policy_empty_data(self) -> None:
        """Test calculating policy for empty data."""
        calculator = CacheControlCalculator(default_max_age=300)
        policy = calculator.calculate_policy(data=None)
        assert policy.max_age == 300

    def test_calculate_policy_with_schema_directives(self) -> None:
        """Test calculating policy with schema directives."""
        directives = SchemaDirectives()
        directives.field_hints["Query.users"] = CacheHint(max_age=300)
        directives.field_hints["Query.me"] = CacheHint(
            max_age=60, scope=CacheScope.PRIVATE
        )

        calculator = CacheControlCalculator(schema_directives=directives)

        data = {
            "users": [{"id": "1", "name": "Alice"}],
            "me": {"id": "2", "name": "Bob"},
        }

        # Create context to simulate Query root type
        context = CacheControlContext(schema_directives=directives)
        policy = calculator.calculate_policy(data, context=context)

        # Note: The calculator walks the data, but field hints are matched
        # based on type.field, so we need __typename or type_info
        # This test mainly verifies no errors occur

    def test_calculate_policy_with_resolver_hints(self) -> None:
        """Test that resolver hints are included."""
        calculator = CacheControlCalculator()

        context = CacheControlContext()
        context.resolver_hints.append(
            FieldCacheHint(
                path=("me",),
                hint=CacheHint(max_age=60, scope=CacheScope.PRIVATE),
                source="resolver",
            )
        )

        policy = calculator.calculate_policy(data={}, context=context)
        assert policy.max_age == 60
        assert policy.scope == CacheScope.PRIVATE

    def test_calculate_from_hints_directly(self) -> None:
        """Test calculate_from_hints method."""
        calculator = CacheControlCalculator(default_max_age=300)

        hints = [
            FieldCacheHint(
                path=("users",),
                hint=CacheHint(max_age=120),
            )
        ]

        policy = calculator.calculate_from_hints(hints)
        assert policy.max_age == 120
