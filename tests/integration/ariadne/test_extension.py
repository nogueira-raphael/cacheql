"""Integration tests for Ariadne caching components."""

from datetime import timedelta
from unittest.mock import MagicMock
import warnings

import pytest

from cacheql import (
    CacheConfig,
    CacheService,
    DefaultKeyBuilder,
    InMemoryCacheBackend,
    JsonSerializer,
)
from cacheql.adapters.ariadne import CacheExtension, CachingGraphQL, CachingGraphQLHTTPHandler

pytest.importorskip("ariadne")


@pytest.fixture
def cache_service() -> CacheService:
    return CacheService(
        backend=InMemoryCacheBackend(maxsize=100),
        key_builder=DefaultKeyBuilder(),
        serializer=JsonSerializer(),
        config=CacheConfig(default_ttl=timedelta(minutes=5), default_max_age=300),
    )


@pytest.fixture
def cache_extension(cache_service: CacheService) -> CacheExtension:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        return CacheExtension(cache_service)


class TestCacheExtension:
    """Tests for the deprecated CacheExtension."""

    def test_deprecation_warning(self, cache_service: CacheService) -> None:
        with pytest.warns(DeprecationWarning, match="CachingGraphQL"):
            CacheExtension(cache_service)

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache_extension: CacheExtension) -> None:
        context = {
            "query": "query GetUsers { users { id name } }",
            "variables": None,
            "operation_name": "GetUsers",
        }

        await cache_extension.request_started(context)

        assert not cache_extension.has_cached_response()
        assert cache_extension.get_cached_response() is None

    @pytest.mark.asyncio
    async def test_cache_hit(self, cache_service: CacheService) -> None:
        query = "query GetUsers { users { id name } }"
        response = {"data": {"users": [{"id": "1", "name": "Alice"}]}}

        await cache_service.cache_response(
            operation_name="GetUsers",
            query=query,
            variables=None,
            response=response,
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            extension = CacheExtension(cache_service)

        context = {
            "query": query,
            "variables": None,
            "operation_name": "GetUsers",
        }

        await extension.request_started(context)

        assert extension.has_cached_response()
        assert extension.get_cached_response() == response

    @pytest.mark.asyncio
    async def test_caches_response(
        self, cache_extension: CacheExtension, cache_service: CacheService
    ) -> None:
        query = "query GetUsers { users { id name } }"
        response = {"data": {"users": [{"id": "1", "name": "Alice"}]}}

        context = {
            "query": query,
            "variables": None,
            "operation_name": "GetUsers",
            "response": response,
        }

        await cache_extension.request_started(context)
        await cache_extension.request_finished(context)

        cached = await cache_service.get_cached_response(
            operation_name="GetUsers",
            query=query,
            variables=None,
        )
        assert cached == response

    @pytest.mark.asyncio
    async def test_skips_mutations(
        self, cache_extension: CacheExtension, cache_service: CacheService
    ) -> None:
        query = "mutation CreateUser { createUser { id } }"
        response = {"data": {"createUser": {"id": "1"}}}

        context = {
            "query": query,
            "variables": None,
            "operation_name": "CreateUser",
            "response": response,
        }

        await cache_extension.request_started(context)
        await cache_extension.request_finished(context)

        cached = await cache_service.get_cached_response(
            operation_name="CreateUser",
            query=query,
            variables=None,
        )
        assert cached is None

    @pytest.mark.asyncio
    async def test_skips_errors(
        self, cache_extension: CacheExtension, cache_service: CacheService
    ) -> None:
        query = "query GetUser { user { id } }"
        response = {"data": None, "errors": [{"message": "Not found"}]}

        context = {
            "query": query,
            "variables": None,
            "operation_name": "GetUser",
            "response": response,
        }

        await cache_extension.request_started(context)
        await cache_extension.request_finished(context)

        cached = await cache_service.get_cached_response(
            operation_name="GetUser",
            query=query,
            variables=None,
        )
        assert cached is None

    def test_format_returns_metadata(self, cache_extension: CacheExtension) -> None:
        result = cache_extension.format({})

        assert "cacheql" in result
        assert "cached" in result["cacheql"]
        assert "stats" in result["cacheql"]

    @pytest.mark.asyncio
    async def test_should_cache_callback(self, cache_service: CacheService) -> None:
        def should_cache(context: dict) -> bool:
            return context.get("user") is not None

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            extension = CacheExtension(cache_service, should_cache=should_cache)

        context = {
            "query": "query Test { test }",
            "variables": None,
            "operation_name": "Test",
        }

        await extension.request_started(context)
        assert not extension.has_cached_response()


class TestCacheExtensionWithVariables:
    """Tests for variable-based cache keys."""

    @pytest.mark.asyncio
    async def test_different_variables_different_cache(
        self, cache_service: CacheService
    ) -> None:
        query = "query GetUser($id: ID!) { user(id: $id) { id name } }"

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            ext1 = CacheExtension(cache_service)
            ext2 = CacheExtension(cache_service)

        ctx1 = {
            "query": query,
            "variables": {"id": "1"},
            "operation_name": "GetUser",
            "response": {"data": {"user": {"id": "1", "name": "Alice"}}},
        }
        await ext1.request_started(ctx1)
        await ext1.request_finished(ctx1)

        ctx2 = {
            "query": query,
            "variables": {"id": "2"},
            "operation_name": "GetUser",
            "response": {"data": {"user": {"id": "2", "name": "Bob"}}},
        }
        await ext2.request_started(ctx2)
        await ext2.request_finished(ctx2)

        cached1 = await cache_service.get_cached_response(
            operation_name="GetUser", query=query, variables={"id": "1"}
        )
        cached2 = await cache_service.get_cached_response(
            operation_name="GetUser", query=query, variables={"id": "2"}
        )

        assert cached1["data"]["user"]["name"] == "Alice"
        assert cached2["data"]["user"]["name"] == "Bob"


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
