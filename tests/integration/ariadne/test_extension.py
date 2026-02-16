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
