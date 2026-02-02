"""Tests for DefaultKeyBuilder."""

import pytest

from cacheql.infrastructure.key_builders.default import DefaultKeyBuilder


class TestDefaultKeyBuilder:
    """Tests for DefaultKeyBuilder."""

    @pytest.fixture
    def key_builder(self) -> DefaultKeyBuilder:
        """Create a key builder for testing."""
        return DefaultKeyBuilder(prefix="test")

    def test_build_basic_key(self, key_builder: DefaultKeyBuilder) -> None:
        """Test building a basic cache key."""
        key = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables=None,
        )

        assert key.startswith("test:GetUser:q:")
        assert "v:" not in key  # No variables

    def test_build_key_with_variables(self, key_builder: DefaultKeyBuilder) -> None:
        """Test building a key with variables."""
        key = key_builder.build(
            operation_name="GetUser",
            query="query GetUser($id: ID!) { user(id: $id) { id } }",
            variables={"id": "123"},
        )

        assert key.startswith("test:GetUser:q:")
        assert ":v:" in key

    def test_build_key_with_context(self, key_builder: DefaultKeyBuilder) -> None:
        """Test building a key with context."""
        key = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables=None,
            context={"user_id": "456"},
        )

        assert ":c:" in key

    def test_build_key_without_operation_name(
        self, key_builder: DefaultKeyBuilder
    ) -> None:
        """Test building a key without operation name."""
        key = key_builder.build(
            operation_name=None,
            query="{ user { id } }",
            variables=None,
        )

        assert key.startswith("test:q:")
        # No operation name in key

    def test_same_query_same_key(self, key_builder: DefaultKeyBuilder) -> None:
        """Test that same query produces same key."""
        key1 = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables={"id": "123"},
        )
        key2 = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables={"id": "123"},
        )

        assert key1 == key2

    def test_different_variables_different_key(
        self, key_builder: DefaultKeyBuilder
    ) -> None:
        """Test that different variables produce different keys."""
        key1 = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables={"id": "1"},
        )
        key2 = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables={"id": "2"},
        )

        assert key1 != key2

    def test_query_normalization(self, key_builder: DefaultKeyBuilder) -> None:
        """Test that equivalent queries with different whitespace produce same key."""
        key1 = key_builder.build(
            operation_name=None,
            query="query GetUser { user { id } }",
            variables=None,
        )
        key2 = key_builder.build(
            operation_name=None,
            query="query   GetUser  {  user  {  id  }  }",
            variables=None,
        )

        assert key1 == key2

    def test_build_field_key(self, key_builder: DefaultKeyBuilder) -> None:
        """Test building a field-level cache key."""
        key = key_builder.build_field_key(
            type_name="User",
            field_name="posts",
            args={"limit": 10},
            parent_value={"id": "123"},
        )

        assert key.startswith("test:field:User:posts:")
        assert ":a:" in key  # Has args
        assert ":p:" in key  # Has parent

    def test_build_field_key_without_args(
        self, key_builder: DefaultKeyBuilder
    ) -> None:
        """Test building a field key without args."""
        key = key_builder.build_field_key(
            type_name="User",
            field_name="name",
            args=None,
            parent_value={"id": "123"},
        )

        assert ":a:" not in key

    def test_exclude_operation_name(self) -> None:
        """Test excluding operation name from key."""
        key_builder = DefaultKeyBuilder(
            prefix="test",
            include_operation_name=False,
        )

        key = key_builder.build(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables=None,
        )

        assert "GetUser" not in key
