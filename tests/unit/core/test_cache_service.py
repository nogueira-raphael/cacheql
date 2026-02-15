"""Tests for CacheService."""

from datetime import timedelta

import pytest

from cacheql import (
    CacheConfig,
    CacheService,
    DefaultKeyBuilder,
    InMemoryCacheBackend,
    JsonSerializer,
)


@pytest.fixture
def cache_service() -> CacheService:
    """Create a cache service for testing."""
    backend = InMemoryCacheBackend(maxsize=100)
    key_builder = DefaultKeyBuilder()
    serializer = JsonSerializer()
    config = CacheConfig(default_ttl=timedelta(minutes=5))

    return CacheService(
        backend=backend,
        key_builder=key_builder,
        serializer=serializer,
        config=config,
    )


class TestCacheService:
    """Tests for CacheService."""

    @pytest.mark.asyncio
    async def test_cache_and_retrieve_response(
        self, cache_service: CacheService
    ) -> None:
        """Test caching and retrieving a response."""
        query = "query GetUser { user { id name } }"
        variables = {"id": "123"}
        response = {"data": {"user": {"id": "123", "name": "Alice"}}}

        # Cache the response
        await cache_service.cache_response(
            operation_name="GetUser",
            query=query,
            variables=variables,
            response=response,
        )

        # Retrieve the cached response
        cached = await cache_service.get_cached_response(
            operation_name="GetUser",
            query=query,
            variables=variables,
        )

        assert cached == response

    @pytest.mark.asyncio
    async def test_cache_miss(self, cache_service: CacheService) -> None:
        """Test cache miss returns None."""
        cached = await cache_service.get_cached_response(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables=None,
        )

        assert cached is None

    @pytest.mark.asyncio
    async def test_different_variables_different_cache(
        self, cache_service: CacheService
    ) -> None:
        """Test that different variables create different cache entries."""
        query = "query GetUser($id: ID!) { user(id: $id) { id name } }"

        # Cache response for user 1
        await cache_service.cache_response(
            operation_name="GetUser",
            query=query,
            variables={"id": "1"},
            response={"data": {"user": {"id": "1", "name": "Alice"}}},
        )

        # Cache response for user 2
        await cache_service.cache_response(
            operation_name="GetUser",
            query=query,
            variables={"id": "2"},
            response={"data": {"user": {"id": "2", "name": "Bob"}}},
        )

        # Retrieve each
        cached1 = await cache_service.get_cached_response(
            operation_name="GetUser",
            query=query,
            variables={"id": "1"},
        )
        cached2 = await cache_service.get_cached_response(
            operation_name="GetUser",
            query=query,
            variables={"id": "2"},
        )

        assert cached1["data"]["user"]["name"] == "Alice"
        assert cached2["data"]["user"]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_cache_with_tags(self, cache_service: CacheService) -> None:
        """Test caching with tags."""
        query = "query GetUser { user { id name } }"
        response = {"data": {"user": {"id": "123", "name": "Alice"}}}

        entry = await cache_service.cache_response(
            operation_name="GetUser",
            query=query,
            variables=None,
            response=response,
            tags=["User", "User:123"],
        )

        assert entry.tags == ("User", "User:123")

    @pytest.mark.asyncio
    async def test_cache_stats(self, cache_service: CacheService) -> None:
        """Test cache statistics tracking."""
        query = "query Test { test }"

        # Initial stats
        assert cache_service.stats["hits"] == 0
        assert cache_service.stats["misses"] == 0

        # Miss
        await cache_service.get_cached_response(
            operation_name=None,
            query=query,
            variables=None,
        )
        assert cache_service.stats["misses"] == 1

        # Cache response
        await cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response={"data": {"test": "value"}},
        )

        # Hit
        await cache_service.get_cached_response(
            operation_name=None,
            query=query,
            variables=None,
        )
        assert cache_service.stats["hits"] == 1

    @pytest.mark.asyncio
    async def test_clear_cache(self, cache_service: CacheService) -> None:
        """Test clearing the cache."""
        query = "query Test { test }"
        await cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response={"data": {"test": "value"}},
        )

        # Verify cached
        cached = await cache_service.get_cached_response(
            operation_name=None,
            query=query,
            variables=None,
        )
        assert cached is not None

        # Clear
        await cache_service.clear()

        # Verify cleared
        cached = await cache_service.get_cached_response(
            operation_name=None,
            query=query,
            variables=None,
        )
        assert cached is None

    @pytest.mark.asyncio
    async def test_different_context_different_cache(
        self, cache_service: CacheService
    ) -> None:
        """Test that different context produces different cache entries."""
        query = "query Me { me { id name } }"

        # Cache response for user 1
        await cache_service.cache_response(
            operation_name="Me",
            query=query,
            variables=None,
            response={"data": {"me": {"id": "1", "name": "Alice"}}},
            context={"current_user_id": "1"},
        )

        # Cache response for user 2
        await cache_service.cache_response(
            operation_name="Me",
            query=query,
            variables=None,
            response={"data": {"me": {"id": "2", "name": "Bob"}}},
            context={"current_user_id": "2"},
        )

        # Each user gets their own cached response
        cached1 = await cache_service.get_cached_response(
            operation_name="Me",
            query=query,
            variables=None,
            context={"current_user_id": "1"},
        )
        cached2 = await cache_service.get_cached_response(
            operation_name="Me",
            query=query,
            variables=None,
            context={"current_user_id": "2"},
        )

        assert cached1["data"]["me"]["name"] == "Alice"
        assert cached2["data"]["me"]["name"] == "Bob"

    @pytest.mark.asyncio
    async def test_no_context_does_not_match_context(
        self, cache_service: CacheService
    ) -> None:
        """Test that cache without context misses when context is given."""
        query = "query Me { me { id name } }"

        # Cache without context
        await cache_service.cache_response(
            operation_name="Me",
            query=query,
            variables=None,
            response={"data": {"me": {"id": "1", "name": "Alice"}}},
        )

        # Lookup with context should miss
        cached = await cache_service.get_cached_response(
            operation_name="Me",
            query=query,
            variables=None,
            context={"current_user_id": "1"},
        )

        assert cached is None

    @pytest.mark.asyncio
    async def test_disabled_cache(self) -> None:
        """Test that disabled cache always returns None."""
        config = CacheConfig(enabled=False)
        cache_service = CacheService(
            backend=InMemoryCacheBackend(),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=config,
        )

        query = "query Test { test }"
        await cache_service.cache_response(
            operation_name=None,
            query=query,
            variables=None,
            response={"data": {"test": "value"}},
        )

        cached = await cache_service.get_cached_response(
            operation_name=None,
            query=query,
            variables=None,
        )

        assert cached is None
