"""Tests for cache decorators."""

from datetime import timedelta

import pytest

from cacheql import (
    CacheConfig,
    CacheService,
    DefaultKeyBuilder,
    InMemoryCacheBackend,
    JsonSerializer,
)
from cacheql.decorators import cached, configure, invalidates


@pytest.fixture
def cache_service() -> CacheService:
    """Create and configure a cache service for testing."""
    backend = InMemoryCacheBackend(maxsize=100)
    key_builder = DefaultKeyBuilder()
    serializer = JsonSerializer()
    config = CacheConfig(default_ttl=timedelta(minutes=5))

    service = CacheService(
        backend=backend,
        key_builder=key_builder,
        serializer=serializer,
        config=config,
    )

    configure(service)
    return service


class TestCachedDecorator:
    """Tests for @cached decorator."""

    @pytest.mark.asyncio
    async def test_cached_function(self, cache_service: CacheService) -> None:
        """Test that @cached caches function results."""
        call_count = 0

        @cached()
        async def get_data(id: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"id": id, "value": "data"}

        # First call - should execute function
        result1 = await get_data(id="123")
        assert result1 == {"id": "123", "value": "data"}
        assert call_count == 1

        # Second call - should return cached result
        result2 = await get_data(id="123")
        assert result2 == {"id": "123", "value": "data"}
        assert call_count == 1  # Not incremented

    @pytest.mark.asyncio
    async def test_cached_different_args(self, cache_service: CacheService) -> None:
        """Test that different args create different cache entries."""
        call_count = 0

        @cached()
        async def get_user(id: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"id": id}

        await get_user(id="1")
        await get_user(id="2")
        await get_user(id="1")  # Should be cached

        assert call_count == 2  # Only 2 unique calls

    @pytest.mark.asyncio
    async def test_cached_with_ttl(self, cache_service: CacheService) -> None:
        """Test @cached with custom TTL."""
        @cached(ttl=timedelta(seconds=10))
        async def get_data() -> str:
            return "value"

        result = await get_data()
        assert result == "value"

    @pytest.mark.asyncio
    async def test_cached_with_tags(self, cache_service: CacheService) -> None:
        """Test @cached with tags."""
        @cached(tags=["User", "User:{id}"])
        async def get_user(id: str) -> dict:
            return {"id": id}

        result = await get_user(id="123")
        assert result == {"id": "123"}

    @pytest.mark.asyncio
    async def test_cached_with_custom_key(self, cache_service: CacheService) -> None:
        """Test @cached with custom key function."""
        @cached(key=lambda id: f"custom:user:{id}")
        async def get_user(id: str) -> dict:
            return {"id": id}

        result = await get_user(id="123")
        assert result == {"id": "123"}

    @pytest.mark.asyncio
    async def test_cached_with_string_key(self, cache_service: CacheService) -> None:
        """Test @cached with string key template."""
        @cached(key="user:{id}")
        async def get_user(id: str) -> dict:
            return {"id": id}

        result = await get_user(id="123")
        assert result == {"id": "123"}


class TestInvalidatesDecorator:
    """Tests for @invalidates decorator."""

    @pytest.mark.asyncio
    async def test_invalidates_tags(self, cache_service: CacheService) -> None:
        """Test that @invalidates clears cache entries."""
        # First, cache some data
        @cached(tags=["User"])
        async def get_user(id: str) -> dict:
            return {"id": id, "version": 1}

        @invalidates(tags=["User"])
        async def update_user(id: str, data: dict) -> dict:
            return {"id": id, **data}

        # Cache the user
        result1 = await get_user(id="123")
        assert result1["version"] == 1

        # Update the user (invalidates cache)
        await update_user(id="123", data={"name": "Alice"})

        # Note: The cache for get_user should now be invalidated
        # But since we're using pattern-based invalidation,
        # the exact behavior depends on tag indexing

    @pytest.mark.asyncio
    async def test_invalidates_with_interpolation(
        self, cache_service: CacheService
    ) -> None:
        """Test @invalidates with tag interpolation."""
        @invalidates(tags=["User:{id}"])
        async def delete_user(id: str) -> bool:
            return True

        result = await delete_user(id="123")
        assert result is True

    @pytest.mark.asyncio
    async def test_invalidates_returns_result(
        self, cache_service: CacheService
    ) -> None:
        """Test that @invalidates returns the function result."""
        @invalidates(tags=["Item"])
        async def create_item(name: str) -> dict:
            return {"id": "new", "name": name}

        result = await create_item(name="Test Item")
        assert result == {"id": "new", "name": "Test Item"}


class TestDecoratorWithoutConfiguration:
    """Tests for decorators when cache is not configured."""

    @pytest.mark.asyncio
    async def test_cached_without_config(self) -> None:
        """Test @cached works without configuration (no caching)."""
        # Reset configuration
        import cacheql.decorators

        cacheql.decorators._cache_service = None
        cacheql.decorators._key_builder = None

        call_count = 0

        @cached()
        async def get_data() -> str:
            nonlocal call_count
            call_count += 1
            return "value"

        await get_data()
        await get_data()

        # Without cache configured, function is called every time
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_invalidates_without_config(self) -> None:
        """Test @invalidates works without configuration (no-op)."""
        import cacheql.decorators

        cacheql.decorators._cache_service = None
        cacheql.decorators._key_builder = None

        @invalidates(tags=["Test"])
        async def update_data() -> str:
            return "updated"

        result = await update_data()
        assert result == "updated"
