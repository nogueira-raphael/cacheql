"""Tests for core entities."""

from datetime import datetime, timedelta, timezone

import pytest

from cacheql.core.entities import CacheConfig, CacheEntry, CacheKey


class TestCacheEntry:
    """Tests for CacheEntry entity."""

    def test_create_cache_entry(self) -> None:
        """Test creating a cache entry with factory method."""
        entry = CacheEntry.create(
            key="test:key",
            value={"data": "value"},
            ttl=timedelta(minutes=5),
            tags=["User", "User:123"],
        )

        assert entry.key == "test:key"
        assert entry.value == {"data": "value"}
        assert entry.ttl == timedelta(minutes=5)
        assert entry.tags == ("User", "User:123")
        assert entry.created_at is not None

    def test_cache_entry_expires_at(self) -> None:
        """Test expires_at calculation."""
        entry = CacheEntry.create(
            key="test:key",
            value="value",
            ttl=timedelta(minutes=5),
        )

        assert entry.expires_at is not None
        assert entry.expires_at > entry.created_at

    def test_cache_entry_no_ttl(self) -> None:
        """Test cache entry without TTL."""
        entry = CacheEntry.create(
            key="test:key",
            value="value",
        )

        assert entry.ttl is None
        assert entry.expires_at is None
        assert not entry.is_expired

    def test_cache_entry_is_expired(self) -> None:
        """Test is_expired property."""
        # Create entry with past creation time
        past_time = datetime.now(timezone.utc) - timedelta(hours=1)
        entry = CacheEntry(
            key="test:key",
            value="value",
            created_at=past_time,
            ttl=timedelta(minutes=5),
        )

        assert entry.is_expired

    def test_cache_entry_immutable(self) -> None:
        """Test that CacheEntry is immutable."""
        entry = CacheEntry.create(key="test", value="value")

        with pytest.raises(AttributeError):
            entry.key = "new_key"  # type: ignore


class TestCacheKey:
    """Tests for CacheKey value object."""

    def test_cache_key_str(self) -> None:
        """Test CacheKey string representation."""
        key = CacheKey(
            prefix="cacheql",
            operation_name="GetUser",
            query_hash="abc123",
            variables_hash="def456",
        )

        assert str(key) == "cacheql:GetUser:abc123:def456"

    def test_cache_key_without_operation_name(self) -> None:
        """Test CacheKey without operation name."""
        key = CacheKey(
            prefix="cacheql",
            operation_name=None,
            query_hash="abc123",
            variables_hash="def456",
        )

        assert str(key) == "cacheql:abc123:def456"

    def test_cache_key_with_context(self) -> None:
        """Test CacheKey with context hash."""
        key = CacheKey(
            prefix="cacheql",
            operation_name="GetUser",
            query_hash="abc123",
            variables_hash="def456",
            context_hash="ctx789",
        )

        assert str(key) == "cacheql:GetUser:abc123:def456:ctx789"


class TestCacheConfig:
    """Tests for CacheConfig entity."""

    def test_default_config(self) -> None:
        """Test default configuration values."""
        config = CacheConfig()

        assert config.enabled is True
        assert config.default_ttl == timedelta(minutes=5)
        assert config.max_size == 1000
        assert config.key_prefix == "cacheql"
        assert config.cache_queries is True
        assert config.cache_mutations is False
        assert config.cache_fields is False
        assert config.auto_invalidate_on_mutation is True

    def test_custom_config(self) -> None:
        """Test custom configuration values."""
        config = CacheConfig(
            enabled=False,
            default_ttl=timedelta(hours=1),
            max_size=500,
            key_prefix="myapp",
            cache_mutations=True,
        )

        assert config.enabled is False
        assert config.default_ttl == timedelta(hours=1)
        assert config.max_size == 500
        assert config.key_prefix == "myapp"
        assert config.cache_mutations is True
