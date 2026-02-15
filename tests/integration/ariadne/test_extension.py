"""Integration tests for Ariadne caching components."""

from datetime import timedelta
from unittest.mock import MagicMock

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
        with pytest.raises(Exception):
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
        with pytest.raises(Exception):
            await handler.execute_graphql_query(request, data)


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
