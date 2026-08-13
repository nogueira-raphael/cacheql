"""Integration tests for Ariadne caching components."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from cacheql import (
    CacheConfig,
    CacheService,
    DefaultKeyBuilder,
    InMemoryCacheBackend,
    JsonSerializer,
)
from cacheql.adapters.ariadne import CachingGraphQL, CachingGraphQLHTTPHandler

pytest.importorskip("ariadne")


@pytest.fixture
def cache_service() -> CacheService:
    return CacheService(
        backend=InMemoryCacheBackend(maxsize=100),
        key_builder=DefaultKeyBuilder(),
        serializer=JsonSerializer(),
        config=CacheConfig(default_ttl=timedelta(minutes=5), default_max_age=300),
    )


class TestCachingGraphQLHTTPHandler:
    """Tests for CachingGraphQLHTTPHandler."""

    @pytest.fixture
    def handler(self, cache_service: CacheService) -> CachingGraphQLHTTPHandler:
        return CachingGraphQLHTTPHandler(cache_service=cache_service)

    @pytest.mark.asyncio
    async def test_returns_cached_response(
        self, cache_service: CacheService, handler: CachingGraphQLHTTPHandler
    ) -> None:
        query = "query { users { id } }"
        response = {"data": {"users": [{"id": "1"}]}}

        await cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response=response,
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": query}

        success, result = await handler.execute_graphql_query(request, data)

        assert success is True
        assert result == response
        assert request.state.cache_hit is True

    @pytest.mark.asyncio
    async def test_skips_mutations(
        self, handler: CachingGraphQLHTTPHandler, cache_service: CacheService
    ) -> None:
        query = "mutation { createUser { id } }"
        data = {"query": query}
        request = MagicMock()

        # Mock parent execution
        handler._schema = None

        # Can't fully test without schema, but verify it attempts execution
        with pytest.raises((TypeError, AttributeError)):
            await handler.execute_graphql_query(request, data)

    @pytest.mark.asyncio
    async def test_should_cache_callback(self, cache_service: CacheService) -> None:
        def should_cache(data: dict) -> bool:
            return "skip" not in data.get("query", "")

        handler = CachingGraphQLHTTPHandler(
            cache_service=cache_service,
            should_cache=should_cache,
        )

        query = "query skip { users { id } }"
        response = {"data": {"users": []}}

        await cache_service.cache_response(
            operation_name=None, query=query, variables=None, response=response
        )

        request = MagicMock()
        data = {"query": query}

        # Should skip cache check due to callback
        with pytest.raises((TypeError, AttributeError)):
            await handler.execute_graphql_query(request, data)


class TestScopeAwareCaching:
    """Tests that session_id callback produces scope-aware cache entries."""

    @pytest.fixture
    def ctx_cache_service(self) -> CacheService:
        return CacheService(
            backend=InMemoryCacheBackend(maxsize=100),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=CacheConfig(
                default_ttl=timedelta(minutes=5),
                default_max_age=300,
            ),
        )

    @pytest.mark.asyncio
    async def test_private_query_cached_per_user(
        self, ctx_cache_service: CacheService
    ) -> None:
        """Private cache entries are found via dual lookup per-user."""
        handler = CachingGraphQLHTTPHandler(
            cache_service=ctx_cache_service,
            session_id=lambda ctx: ctx.get("current_user_id"),
        )

        query = "query { me { id name } }"
        user1_response = {"data": {"me": {"id": "1", "name": "Alice"}}}
        user2_response = {"data": {"me": {"id": "2", "name": "Bob"}}}

        # Pre-populate cache with user-specific entries
        await ctx_cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response=user1_response,
            context={"session_id": "1"},
        )
        await ctx_cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response=user2_response,
            context={"session_id": "2"},
        )

        data = {"query": query}

        # User 1 gets their own cached response
        request1 = MagicMock()
        request1.state = MagicMock()
        handler.get_context_for_request = AsyncMock(
            return_value={"current_user_id": "1"}
        )

        success1, result1 = await handler.execute_graphql_query(
            request1, data, context_value=None
        )
        assert success1 is True
        assert result1 == user1_response

        # User 2 gets their own cached response
        request2 = MagicMock()
        request2.state = MagicMock()
        handler.get_context_for_request = AsyncMock(
            return_value={"current_user_id": "2"}
        )

        success2, result2 = await handler.execute_graphql_query(
            request2, data, context_value=None
        )
        assert success2 is True
        assert result2 == user2_response

    @pytest.mark.asyncio
    async def test_public_query_shared_across_users(
        self, ctx_cache_service: CacheService
    ) -> None:
        """Public cache entries are shared across all users."""
        handler = CachingGraphQLHTTPHandler(
            cache_service=ctx_cache_service,
            session_id=lambda ctx: ctx.get("current_user_id"),
        )

        query = "query { users { id name } }"
        shared_response = {"data": {"users": [{"id": "1", "name": "Alice"}]}}

        # Pre-populate cache with a public entry (no context)
        await ctx_cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response=shared_response,
            context=None,
        )

        data = {"query": query}

        # User 1 gets the shared response (private miss → public hit)
        request1 = MagicMock()
        request1.state = MagicMock()
        handler.get_context_for_request = AsyncMock(
            return_value={"current_user_id": "1"}
        )

        success1, result1 = await handler.execute_graphql_query(
            request1, data, context_value=None
        )
        assert success1 is True
        assert result1 == shared_response

        # User 2 also gets the same shared response
        request2 = MagicMock()
        request2.state = MagicMock()
        handler.get_context_for_request = AsyncMock(
            return_value={"current_user_id": "2"}
        )

        success2, result2 = await handler.execute_graphql_query(
            request2, data, context_value=None
        )
        assert success2 is True
        assert result2 == shared_response


class TestCachingGraphQL:
    """Tests for CachingGraphQL ASGI app."""

    def test_initialization(self, cache_service: CacheService) -> None:
        from ariadne import make_executable_schema

        type_defs = "type Query { hello: String }"
        schema = make_executable_schema(type_defs)

        app = CachingGraphQL(schema, cache_service=cache_service)

        assert app.cache_service is cache_service
        assert app.cache_stats == {"hits": 0, "misses": 0, "total": 0}

    def test_with_should_cache(self, cache_service: CacheService) -> None:
        from ariadne import make_executable_schema

        type_defs = "type Query { hello: String }"
        schema = make_executable_schema(type_defs)

        def should_cache(data: dict) -> bool:
            return True

        app = CachingGraphQL(
            schema,
            cache_service=cache_service,
            should_cache=should_cache,
        )

        assert app._caching_handler._should_cache is should_cache

    def test_with_session_id(self, cache_service: CacheService) -> None:
        from ariadne import make_executable_schema

        type_defs = "type Query { hello: String }"
        schema = make_executable_schema(type_defs)

        def get_session_id(ctx: dict) -> str | None:
            return ctx.get("user_id")

        app = CachingGraphQL(
            schema,
            cache_service=cache_service,
            session_id=get_session_id,
        )

        assert app._caching_handler._session_id is get_session_id

    def test_passes_kwargs_to_parent(self, cache_service: CacheService) -> None:
        from ariadne import make_executable_schema

        type_defs = "type Query { hello: String }"
        schema = make_executable_schema(type_defs)

        app = CachingGraphQL(
            schema,
            cache_service=cache_service,
            debug=True,
        )

        assert app._caching_handler._debug is True


class TestCacheControlWithRealSchema:
    """End-to-end tests against a real Ariadne schema + resolvers.

    These cover the bugs fixed alongside the scope-aware caching work:
    type-level @cacheControl resolution without __typename, dynamic
    hints from resolvers, automatic tagging of cached responses, and
    tag-based auto-invalidation on mutations.
    """

    def _build(self, type_defs: str, query_type=None, mutation_type=None):
        from ariadne import make_executable_schema

        from cacheql import get_cache_control_directive_sdl

        schema = make_executable_schema(
            get_cache_control_directive_sdl() + type_defs,
            *(t for t in (query_type, mutation_type) if t is not None),
        )
        return schema

    def _fake_request(self):
        class RequestState:
            pass

        class FakeRequest:
            state = RequestState()

        return FakeRequest()

    @pytest.mark.asyncio
    async def test_type_level_directive_applies_without_typename(self) -> None:
        from ariadne import QueryType

        query_type = QueryType()

        @query_type.field("users")
        async def resolve_users(*_):
            return [{"id": "1", "name": "Alice"}]

        schema = self._build(
            """
            type Query { users: [User!]! }
            type User @cacheControl(maxAge: 600) { id: ID! name: String! }
            """,
            query_type,
        )

        cache_service = CacheService(
            backend=InMemoryCacheBackend(maxsize=100),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=CacheConfig(default_max_age=0, calculate_http_headers=True),
        )
        handler = CachingGraphQLHTTPHandler(cache_service=cache_service, schema=schema)
        handler.configure(schema=schema)

        request = self._fake_request()
        # The query never asks for __typename - the old implementation
        # could only see the User type-level directive if it did.
        data = {"query": "query { users { id name } }"}
        success, response = await handler.execute_graphql_query(
            request, data, context_value={}
        )

        assert success is True
        assert request.state.cache_control_header == "max-age=600, public"

    @pytest.mark.asyncio
    async def test_dynamic_hint_from_resolver_is_applied(self) -> None:
        from ariadne import QueryType

        from cacheql.hints import set_cache_hint

        query_type = QueryType()

        @query_type.field("hinted")
        async def resolve_hinted(_, info):
            set_cache_hint(info, max_age=42, scope="PUBLIC")
            return {"id": "1", "name": "Bob"}

        schema = self._build(
            """
            type Query { hinted: User }
            type User { id: ID! name: String! }
            """,
            query_type,
        )

        cache_service = CacheService(
            backend=InMemoryCacheBackend(maxsize=100),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=CacheConfig(default_max_age=0, calculate_http_headers=True),
        )
        handler = CachingGraphQLHTTPHandler(cache_service=cache_service, schema=schema)
        handler.configure(schema=schema)

        request = self._fake_request()
        data = {"query": "query { hinted { id name } }"}
        await handler.execute_graphql_query(request, data, context_value={})

        assert request.state.cache_control_header == "max-age=42, public"

    @pytest.mark.asyncio
    async def test_mutation_auto_invalidates_tagged_query(self) -> None:
        from ariadne import MutationType, QueryType

        query_type = QueryType()
        mutation_type = MutationType()
        state = {"name": "Alice"}

        @query_type.field("user")
        async def resolve_user(_, info, id):
            return {"id": id, "name": state["name"]}

        @mutation_type.field("updateUser")
        async def resolve_update_user(_, info, id):
            state["name"] = "Alice Updated"
            return {"id": id, "name": state["name"]}

        schema = self._build(
            """
            type Query { user(id: ID!): User @cacheControl(maxAge: 300) }
            type Mutation { updateUser(id: ID!): User }
            type User { id: ID! name: String! }
            """,
            query_type,
            mutation_type,
        )

        cache_service = CacheService(
            backend=InMemoryCacheBackend(maxsize=100),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=CacheConfig(
                default_max_age=0, auto_invalidate_on_mutation=True
            ),
        )
        handler = CachingGraphQLHTTPHandler(cache_service=cache_service, schema=schema)
        handler.configure(schema=schema)

        query_data = {"query": 'query { user(id: "1") { id name } }'}

        request1 = self._fake_request()
        _, r1 = await handler.execute_graphql_query(
            request1, query_data, context_value={}
        )
        assert r1["data"]["user"]["name"] == "Alice"

        request2 = self._fake_request()
        _, r2 = await handler.execute_graphql_query(
            request2, query_data, context_value={}
        )
        assert r2["data"]["user"]["name"] == "Alice"  # served from cache

        mutation_data = {"query": 'mutation { updateUser(id: "1") { id name } }'}
        request3 = self._fake_request()
        await handler.execute_graphql_query(
            request3, mutation_data, context_value={}
        )

        request4 = self._fake_request()
        _, r4 = await handler.execute_graphql_query(
            request4, query_data, context_value={}
        )
        assert r4["data"]["user"]["name"] == "Alice Updated"

    @pytest.mark.asyncio
    async def test_mutation_does_not_invalidate_when_disabled(self) -> None:
        from ariadne import MutationType, QueryType

        query_type = QueryType()
        mutation_type = MutationType()
        state = {"name": "Alice"}

        @query_type.field("user")
        async def resolve_user(_, info, id):
            return {"id": id, "name": state["name"]}

        @mutation_type.field("updateUser")
        async def resolve_update_user(_, info, id):
            state["name"] = "Alice Updated"
            return {"id": id, "name": state["name"]}

        schema = self._build(
            """
            type Query { user(id: ID!): User @cacheControl(maxAge: 300) }
            type Mutation { updateUser(id: ID!): User }
            type User { id: ID! name: String! }
            """,
            query_type,
            mutation_type,
        )

        cache_service = CacheService(
            backend=InMemoryCacheBackend(maxsize=100),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=CacheConfig(
                default_max_age=0, auto_invalidate_on_mutation=False
            ),
        )
        handler = CachingGraphQLHTTPHandler(cache_service=cache_service, schema=schema)
        handler.configure(schema=schema)

        query_data = {"query": 'query { user(id: "1") { id name } }'}
        await handler.execute_graphql_query(
            self._fake_request(), query_data, context_value={}
        )

        mutation_data = {"query": 'mutation { updateUser(id: "1") { id name } }'}
        await handler.execute_graphql_query(
            self._fake_request(), mutation_data, context_value={}
        )

        _, r = await handler.execute_graphql_query(
            self._fake_request(), query_data, context_value={}
        )
        assert r["data"]["user"]["name"] == "Alice"  # stale: auto-invalidate is off
