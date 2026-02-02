"""Integration tests for Strawberry CacheExtension."""

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
from cacheql.adapters.strawberry import CacheExtension

# Skip tests if strawberry is not installed
pytest.importorskip("strawberry")


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


@pytest.fixture
def cache_extension(cache_service: CacheService) -> CacheExtension:
    """Create a cache extension for testing."""
    return CacheExtension(cache_service)


class TestCacheExtension:
    """Tests for Strawberry CacheExtension."""

    def test_extension_is_callable(self, cache_extension: CacheExtension) -> None:
        """Test that extension is callable (factory pattern)."""
        mock_context = MagicMock()
        mock_context.query = "query Test { test }"
        mock_context.variables = None
        mock_context.operation_name = "Test"

        instance = cache_extension(execution_context=mock_context)

        assert instance is not None
        assert hasattr(instance, "on_operation")
        assert hasattr(instance, "get_results")

    def test_get_results_returns_metadata(
        self, cache_extension: CacheExtension
    ) -> None:
        """Test that get_results returns cache metadata."""
        mock_context = MagicMock()
        mock_context.query = "query Test { test }"

        instance = cache_extension(execution_context=mock_context)
        results = instance.get_results()

        assert "cacheql" in results
        assert "cached" in results["cacheql"]
        assert "stats" in results["cacheql"]

    def test_custom_should_cache_callback(
        self, cache_service: CacheService
    ) -> None:
        """Test custom should_cache callback."""

        def should_cache(context: MagicMock) -> bool:
            return hasattr(context, "user")

        extension = CacheExtension(cache_service, should_cache=should_cache)

        mock_context = MagicMock()
        mock_context.query = "query Test { test }"

        instance = extension(execution_context=mock_context)
        assert instance is not None


class TestCacheExtensionIntegration:
    """Integration tests requiring full Strawberry setup."""

    @pytest.mark.asyncio
    async def test_cache_service_stats(self, cache_service: CacheService) -> None:
        """Test that cache service tracks stats correctly."""
        # Initial stats
        assert cache_service.stats["hits"] == 0
        assert cache_service.stats["misses"] == 0

        # Miss
        await cache_service.get_cached_response(
            operation_name="Test",
            query="query Test { test }",
            variables=None,
        )
        assert cache_service.stats["misses"] == 1

        # Cache
        await cache_service.cache_response(
            operation_name="Test",
            query="query Test { test }",
            variables=None,
            response={"data": {"test": "value"}},
        )

        # Hit
        await cache_service.get_cached_response(
            operation_name="Test",
            query="query Test { test }",
            variables=None,
        )
        assert cache_service.stats["hits"] == 1
