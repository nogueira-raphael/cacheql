"""Tests for InMemoryCacheBackend."""

from datetime import timedelta

import pytest

from cacheql.infrastructure.backends.memory import InMemoryCacheBackend


class TestInMemoryCacheBackend:
    """Tests for InMemoryCacheBackend."""

    @pytest.fixture
    def backend(self) -> InMemoryCacheBackend:
        """Create a backend for testing."""
        return InMemoryCacheBackend(maxsize=100, default_ttl=300.0)

    @pytest.mark.asyncio
    async def test_set_and_get(self, backend: InMemoryCacheBackend) -> None:
        """Test basic set and get operations."""
        await backend.set("key1", b"value1")
        result = await backend.get("key1")
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_get_missing_key(self, backend: InMemoryCacheBackend) -> None:
        """Test getting a missing key returns None."""
        result = await backend.get("nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, backend: InMemoryCacheBackend) -> None:
        """Test deleting a key."""
        await backend.set("key1", b"value1")

        # Delete existing key
        deleted = await backend.delete("key1")
        assert deleted is True

        # Verify deleted
        result = await backend.get("key1")
        assert result is None

        # Delete non-existing key
        deleted = await backend.delete("key1")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_exists(self, backend: InMemoryCacheBackend) -> None:
        """Test checking if key exists."""
        await backend.set("key1", b"value1")

        assert await backend.exists("key1") is True
        assert await backend.exists("nonexistent") is False

    @pytest.mark.asyncio
    async def test_clear(self, backend: InMemoryCacheBackend) -> None:
        """Test clearing all keys."""
        await backend.set("key1", b"value1")
        await backend.set("key2", b"value2")
        await backend.set("key3", b"value3")

        await backend.clear()

        assert await backend.get("key1") is None
        assert await backend.get("key2") is None
        assert await backend.get("key3") is None
        assert len(backend) == 0

    @pytest.mark.asyncio
    async def test_delete_pattern(self, backend: InMemoryCacheBackend) -> None:
        """Test deleting keys by pattern."""
        await backend.set("user:1", b"alice")
        await backend.set("user:2", b"bob")
        await backend.set("post:1", b"hello")
        await backend.set("post:2", b"world")

        # Delete all user keys
        deleted = await backend.delete_pattern("user:*")
        assert deleted == 2

        # Verify
        assert await backend.get("user:1") is None
        assert await backend.get("user:2") is None
        assert await backend.get("post:1") == b"hello"
        assert await backend.get("post:2") == b"world"

    @pytest.mark.asyncio
    async def test_set_with_ttl(self, backend: InMemoryCacheBackend) -> None:
        """Test setting a key with custom TTL."""
        # Note: InMemoryCacheBackend uses global TTL from TTLCache
        # This test verifies the method accepts TTL parameter
        await backend.set("key1", b"value1", ttl=timedelta(seconds=10))
        result = await backend.get("key1")
        assert result == b"value1"

    @pytest.mark.asyncio
    async def test_lru_eviction(self) -> None:
        """Test LRU eviction when maxsize is reached."""
        backend = InMemoryCacheBackend(maxsize=3, default_ttl=300.0)

        await backend.set("key1", b"value1")
        await backend.set("key2", b"value2")
        await backend.set("key3", b"value3")

        # Access key1 to make it recently used
        await backend.get("key1")

        # Add key4, should evict key2 (least recently used)
        await backend.set("key4", b"value4")

        assert await backend.get("key1") == b"value1"  # Still exists (recently used)
        assert await backend.get("key2") is None  # Evicted
        assert await backend.get("key3") == b"value3"  # Still exists
        assert await backend.get("key4") == b"value4"  # Newly added

    def test_len(self) -> None:
        """Test getting cache size."""
        backend = InMemoryCacheBackend(maxsize=100)
        assert len(backend) == 0

    def test_maxsize_property(self) -> None:
        """Test maxsize property."""
        backend = InMemoryCacheBackend(maxsize=500)
        assert backend.maxsize == 500
