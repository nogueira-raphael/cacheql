"""Tests for DirectiveParser and SchemaDirectives."""

from ariadne import make_executable_schema

from cacheql.core.entities.cache_control import CacheHint, CacheScope
from cacheql.core.services.directive_parser import (
    CACHE_CONTROL_DIRECTIVE,
    DirectiveParser,
    SchemaDirectives,
    get_cache_control_directive_sdl,
)


class TestGetCacheControlDirectiveSdl:
    """Tests for get_cache_control_directive_sdl function."""

    def test_returns_directive_definition(self):
        """Should return the cache control directive SDL."""
        sdl = get_cache_control_directive_sdl()
        assert "directive @cacheControl" in sdl
        assert "maxAge: Int" in sdl
        assert "scope: CacheControlScope" in sdl
        assert "inheritMaxAge: Boolean" in sdl

    def test_returns_scope_enum(self):
        """Should include the CacheControlScope enum."""
        sdl = get_cache_control_directive_sdl()
        assert "enum CacheControlScope" in sdl
        assert "PUBLIC" in sdl
        assert "PRIVATE" in sdl

    def test_matches_constant(self):
        """Should match the CACHE_CONTROL_DIRECTIVE constant."""
        assert get_cache_control_directive_sdl() == CACHE_CONTROL_DIRECTIVE


class TestSchemaDirectives:
    """Tests for SchemaDirectives class."""

    def test_empty_directives(self):
        """Should initialize with empty dicts."""
        directives = SchemaDirectives()
        assert directives.type_hints == {}
        assert directives.field_hints == {}

    def test_get_hint_for_type_exists(self):
        """Should return hint for type with explicit directive."""
        directives = SchemaDirectives(
            type_hints={"User": CacheHint(max_age=300, scope=CacheScope.PUBLIC)}
        )
        hint = directives.get_hint_for_type("User")
        assert hint is not None
        assert hint.max_age == 300
        assert hint.scope == CacheScope.PUBLIC

    def test_get_hint_for_type_not_exists(self):
        """Should return None for type without directive."""
        directives = SchemaDirectives()
        hint = directives.get_hint_for_type("User")
        assert hint is None

    def test_get_hint_for_field_explicit_directive(self):
        """Should return hint for field with explicit directive."""
        directives = SchemaDirectives(
            field_hints={"User.email": CacheHint(max_age=60, scope=CacheScope.PRIVATE)}
        )
        hint = directives.get_hint_for_field("User", "email")
        assert hint is not None
        assert hint.max_age == 60
        assert hint.scope == CacheScope.PRIVATE

    def test_get_hint_for_field_falls_back_to_type(self):
        """Should fall back to type hint if field hint not found."""
        directives = SchemaDirectives(
            type_hints={"User": CacheHint(max_age=600, scope=CacheScope.PUBLIC)}
        )
        hint = directives.get_hint_for_field("User", "name")
        assert hint is not None
        assert hint.max_age == 600
        assert hint.scope == CacheScope.PUBLIC

    def test_get_hint_for_field_not_exists(self):
        """Should return None if no hint for field or type."""
        directives = SchemaDirectives()
        hint = directives.get_hint_for_field("User", "name")
        assert hint is None

    def test_get_hint_for_field_with_inherit_max_age(self):
        """Should inherit maxAge from parent when inheritMaxAge is set."""
        directives = SchemaDirectives(
            field_hints={
                "Post.author": CacheHint(
                    max_age=None, scope=CacheScope.PUBLIC, inherit_max_age=True
                )
            }
        )
        parent_hint = CacheHint(max_age=300, scope=CacheScope.PUBLIC)
        hint = directives.get_hint_for_field("Post", "author", parent_hint=parent_hint)

        assert hint is not None
        assert hint.max_age == 300  # Inherited from parent
        assert hint.scope == CacheScope.PUBLIC
        assert hint.inherit_max_age is False  # Reset after inheritance

    def test_get_hint_for_field_inherit_without_parent(self):
        """Should return original hint if inheritMaxAge but no parent."""
        directives = SchemaDirectives(
            field_hints={
                "Post.author": CacheHint(
                    max_age=None, scope=CacheScope.PUBLIC, inherit_max_age=True
                )
            }
        )
        hint = directives.get_hint_for_field("Post", "author", parent_hint=None)

        assert hint is not None
        assert hint.max_age is None
        assert hint.inherit_max_age is True

    def test_get_hint_for_field_inherit_scope_from_field(self):
        """Should use field scope when inheriting maxAge from parent."""
        directives = SchemaDirectives(
            field_hints={
                "User.profile": CacheHint(
                    max_age=None, scope=CacheScope.PRIVATE, inherit_max_age=True
                )
            }
        )
        parent_hint = CacheHint(max_age=600, scope=CacheScope.PUBLIC)
        hint = directives.get_hint_for_field("User", "profile", parent_hint=parent_hint)

        assert hint is not None
        assert hint.max_age == 600  # From parent
        assert hint.scope == CacheScope.PRIVATE  # From field directive

    def test_field_hint_takes_precedence_over_type(self):
        """Field directive should take precedence over type directive."""
        directives = SchemaDirectives(
            type_hints={"User": CacheHint(max_age=600, scope=CacheScope.PUBLIC)},
            field_hints={"User.email": CacheHint(max_age=60, scope=CacheScope.PRIVATE)},
        )
        hint = directives.get_hint_for_field("User", "email")
        assert hint.max_age == 60
        assert hint.scope == CacheScope.PRIVATE


class TestDirectiveParser:
    """Tests for DirectiveParser class."""

    def test_default_max_age(self):
        """Should initialize with default_max_age."""
        parser = DirectiveParser(default_max_age=300)
        assert parser._default_max_age == 300

    def test_parse_schema_with_type_directive(self):
        """Should parse @cacheControl on types."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                user: User
            }

            type User @cacheControl(maxAge: 600) {
                id: ID!
                name: String!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert "User" in directives.type_hints
        hint = directives.type_hints["User"]
        assert hint.max_age == 600

    def test_parse_schema_with_field_directive(self):
        """Should parse @cacheControl on fields."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                users: [User!]! @cacheControl(maxAge: 300)
            }

            type User {
                id: ID!
                name: String!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert "Query.users" in directives.field_hints
        hint = directives.field_hints["Query.users"]
        assert hint.max_age == 300

    def test_parse_schema_with_scope_private(self):
        """Should parse scope: PRIVATE directive."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                me: User @cacheControl(maxAge: 60, scope: PRIVATE)
            }

            type User {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Query.me"]
        assert hint.max_age == 60
        assert hint.scope == CacheScope.PRIVATE

    def test_parse_schema_with_scope_public(self):
        """Should parse scope: PUBLIC directive."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                posts: [Post!]! @cacheControl(maxAge: 300, scope: PUBLIC)
            }

            type Post {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Query.posts"]
        assert hint.max_age == 300
        assert hint.scope == CacheScope.PUBLIC

    def test_parse_schema_with_inherit_max_age(self):
        """Should parse inheritMaxAge: true directive."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                post: Post
            }

            type Post {
                id: ID!
                author: User @cacheControl(inheritMaxAge: true)
            }

            type User {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Post.author"]
        assert hint.inherit_max_age is True

    def test_parse_schema_without_directives(self):
        """Should return empty hints for schema without directives."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                user: User
            }

            type User {
                id: ID!
                name: String!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert directives.type_hints == {}
        assert directives.field_hints == {}

    def test_parse_schema_with_nested_types(self):
        """Should parse directives on nested types and fields."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                posts: [Post!]! @cacheControl(maxAge: 300)
            }

            type Post @cacheControl(maxAge: 300) {
                id: ID!
                title: String!
                author: User @cacheControl(inheritMaxAge: true)
                comments: [Comment!]! @cacheControl(maxAge: 60)
            }

            type User @cacheControl(maxAge: 600) {
                id: ID!
                name: String!
                email: String! @cacheControl(scope: PRIVATE)
            }

            type Comment @cacheControl(maxAge: 120) {
                id: ID!
                text: String!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        # Type hints
        assert "Post" in directives.type_hints
        assert directives.type_hints["Post"].max_age == 300
        assert "User" in directives.type_hints
        assert directives.type_hints["User"].max_age == 600
        assert "Comment" in directives.type_hints
        assert directives.type_hints["Comment"].max_age == 120

        # Field hints
        assert "Query.posts" in directives.field_hints
        assert directives.field_hints["Query.posts"].max_age == 300
        assert "Post.author" in directives.field_hints
        assert directives.field_hints["Post.author"].inherit_max_age is True
        assert "Post.comments" in directives.field_hints
        assert directives.field_hints["Post.comments"].max_age == 60
        assert "User.email" in directives.field_hints
        assert directives.field_hints["User.email"].scope == CacheScope.PRIVATE

    def test_parse_schema_skips_builtin_types(self):
        """Should skip introspection types (__Type, __Schema, etc.)."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                user: User
            }

            type User @cacheControl(maxAge: 600) {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        # Should not include any __* types
        for type_name in directives.type_hints:
            assert not type_name.startswith("__")

    def test_parse_schema_with_multiple_fields_same_type(self):
        """Should parse multiple fields with directives on same type."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                publicData: String @cacheControl(maxAge: 3600, scope: PUBLIC)
                privateData: String @cacheControl(maxAge: 60, scope: PRIVATE)
                noCache: String @cacheControl(maxAge: 0)
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert directives.field_hints["Query.publicData"].max_age == 3600
        assert directives.field_hints["Query.publicData"].scope == CacheScope.PUBLIC
        assert directives.field_hints["Query.privateData"].max_age == 60
        assert directives.field_hints["Query.privateData"].scope == CacheScope.PRIVATE
        assert directives.field_hints["Query.noCache"].max_age == 0

    def test_parse_schema_with_only_scope(self):
        """Should parse directive with only scope, no maxAge."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                me: User
            }

            type User {
                id: ID!
                email: String! @cacheControl(scope: PRIVATE)
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["User.email"]
        assert hint.max_age is None
        assert hint.scope == CacheScope.PRIVATE

    def test_parse_schema_with_only_max_age(self):
        """Should parse directive with only maxAge, no scope."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                users: [User!]! @cacheControl(maxAge: 300)
            }

            type User {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Query.users"]
        assert hint.max_age == 300
        assert hint.scope is None


class TestDirectiveParserEdgeCases:
    """Edge case tests for DirectiveParser."""

    def test_parse_non_graphql_schema(self):
        """Should return empty directives for non-GraphQL schema object."""
        parser = DirectiveParser()
        directives = parser.parse_schema("not a schema")
        assert directives.type_hints == {}
        assert directives.field_hints == {}

    def test_parse_none_schema(self):
        """Should return empty directives for None schema."""
        parser = DirectiveParser()
        directives = parser.parse_schema(None)
        assert directives.type_hints == {}
        assert directives.field_hints == {}

    def test_parse_empty_dict(self):
        """Should return empty directives for empty dict."""
        parser = DirectiveParser()
        directives = parser.parse_schema({})
        assert directives.type_hints == {}
        assert directives.field_hints == {}

    def test_parse_schema_with_interface(self):
        """Should parse directives on interface types."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                node: Node
            }

            interface Node @cacheControl(maxAge: 300) {
                id: ID!
            }

            type User implements Node {
                id: ID!
                name: String!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert "Node" in directives.type_hints
        assert directives.type_hints["Node"].max_age == 300

    def test_parse_schema_with_union(self):
        """Should parse directives on union types."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                search: SearchResult
            }

            union SearchResult @cacheControl(maxAge: 60) = User | Post

            type User {
                id: ID!
            }

            type Post {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert "SearchResult" in directives.type_hints
        assert directives.type_hints["SearchResult"].max_age == 60

    def test_parse_schema_mutation_fields(self):
        """Should parse directives on mutation fields."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                user: User
            }

            type Mutation {
                updateUser(id: ID!): User @cacheControl(maxAge: 0)
            }

            type User {
                id: ID!
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        assert "Mutation.updateUser" in directives.field_hints
        assert directives.field_hints["Mutation.updateUser"].max_age == 0

    def test_parse_schema_with_all_parameters(self):
        """Should parse directive with all parameters specified."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                data: String @cacheControl(
                    maxAge: 300, scope: PRIVATE, inheritMaxAge: false
                )
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Query.data"]
        assert hint.max_age == 300
        assert hint.scope == CacheScope.PRIVATE
        assert hint.inherit_max_age is False

    def test_parse_schema_max_age_zero(self):
        """Should correctly parse maxAge: 0 (no caching)."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                sensitive: String @cacheControl(maxAge: 0)
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Query.sensitive"]
        assert hint.max_age == 0

    def test_parse_schema_large_max_age(self):
        """Should correctly parse large maxAge values."""
        type_defs = (
            get_cache_control_directive_sdl()
            + """
            type Query {
                static: String @cacheControl(maxAge: 31536000)
            }
        """
        )
        schema = make_executable_schema(type_defs)
        parser = DirectiveParser()

        directives = parser.parse_schema(schema)

        hint = directives.field_hints["Query.static"]
        assert hint.max_age == 31536000  # 1 year in seconds
