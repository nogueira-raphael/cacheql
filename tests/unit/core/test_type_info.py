"""Tests for build_type_info (query AST + schema -> response path types)."""

import pytest

graphql = pytest.importorskip("graphql")

from graphql import build_schema  # noqa: E402

from cacheql.core.services.type_info import build_type_info  # noqa: E402

SCHEMA = build_schema(
    """
    type Query {
      users: [User!]!
      me: User
      search: SearchResult
    }
    type Mutation {
      updateUser(id: ID!): User
    }
    interface Node {
      id: ID!
    }
    type User implements Node {
      id: ID!
      name: String!
      posts: [Post!]!
    }
    type Post implements Node {
      id: ID!
      title: String!
      author: User!
    }
    union SearchResult = User | Post
    """
)


class TestBuildTypeInfo:
    def test_resolves_top_level_field_type(self) -> None:
        type_info = build_type_info(SCHEMA, "query { users { id } }")
        assert type_info["users"] == "User"

    def test_resolves_nested_field_type(self) -> None:
        query = "query { users { posts { author { id } } } }"
        type_info = build_type_info(SCHEMA, query)
        assert type_info["users.posts"] == "Post"
        assert type_info["users.posts.author"] == "User"

    def test_uses_response_key_alias_not_field_name(self) -> None:
        query = "query { me { id } aliased: me { id } }"
        type_info = build_type_info(SCHEMA, query)
        assert type_info["me"] == "User"
        assert type_info["aliased"] == "User"
        assert "me.id" in type_info
        assert "aliased.id" in type_info

    def test_resolves_through_inline_fragments(self) -> None:
        query = """
        query {
          search {
            ... on User { name }
            ... on Post { title }
          }
        }
        """
        type_info = build_type_info(SCHEMA, query)
        assert type_info["search"] == "SearchResult"
        assert type_info["search.name"] == "String"
        assert type_info["search.title"] == "String"

    def test_resolves_through_fragment_spread(self) -> None:
        query = """
        query {
          users { ...UserFields }
        }
        fragment UserFields on User {
          name
        }
        """
        type_info = build_type_info(SCHEMA, query)
        assert type_info["users.name"] == "String"

    def test_selects_operation_by_name(self) -> None:
        query = """
        query GetUsers { users { id } }
        mutation UpdateUser($id: ID!) { updateUser(id: $id) { id } }
        """
        type_info = build_type_info(SCHEMA, query, operation_name="UpdateUser")
        assert type_info["updateUser"] == "User"

    def test_skips_introspection_fields(self) -> None:
        type_info = build_type_info(SCHEMA, "query { __typename users { id } }")
        assert "__typename" not in type_info
        assert type_info["users"] == "User"

    def test_invalid_query_returns_empty_mapping(self) -> None:
        assert build_type_info(SCHEMA, "not a query {") == {}

    def test_unknown_operation_name_falls_back(self) -> None:
        query = "query GetUsers { users { id } }"
        type_info = build_type_info(SCHEMA, query, operation_name="DoesNotExist")
        assert type_info["users"] == "User"
