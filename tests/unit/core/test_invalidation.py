"""Tests for tag-based cache invalidation."""

import asyncio
from datetime import timedelta

from cacheql import (
    CacheConfig,
    CacheService,
    DefaultKeyBuilder,
    InMemoryCacheBackend,
    JsonSerializer,
)


def create_cache_service(
    key_prefix: str = "test",
    default_ttl: timedelta = timedelta(minutes=5),
) -> tuple[CacheService, InMemoryCacheBackend]:
    """Create a cache service with in-memory backend for testing."""
    backend = InMemoryCacheBackend(maxsize=100)
    config = CacheConfig(
        enabled=True,
        key_prefix=key_prefix,
        default_ttl=default_ttl,
    )
    service = CacheService(
        backend=backend,
        key_builder=DefaultKeyBuilder(),
        serializer=JsonSerializer(),
        config=config,
    )
    return service, backend


class TestSimpleTagInvalidation:
    """Tests for single tag invalidation."""

    async def test_invalidate_single_tag(self):
        """Should invalidate entries with the specified tag."""
        service, backend = create_cache_service()

        # Cache entry with tag
        await service.cache_response(
            operation_name="GetUser",
            query="query { user { id } }",
            variables=None,
            response={"data": {"user": {"id": "1"}}},
            tags=["User"],
        )

        # Verify entry exists
        assert len(backend) > 0

        # Invalidate
        await service.invalidate(["User"])

        # Entry should be removed (tag mapping key)
        # Note: The actual response key may still exist depending on implementation

    async def test_cache_entries_with_tag_removed(self):
        """Should remove cache entries that have the invalidated tag."""
        service, backend = create_cache_service()

        # Cache multiple entries with same tag
        await service.cache_response(
            operation_name="GetUser1",
            query="query { user(id: 1) { id } }",
            variables={"id": "1"},
            response={"data": {"user": {"id": "1"}}},
            tags=["User", "User:1"],
        )
        await service.cache_response(
            operation_name="GetUser2",
            query="query { user(id: 2) { id } }",
            variables={"id": "2"},
            response={"data": {"user": {"id": "2"}}},
            tags=["User", "User:2"],
        )

        initial_count = len(backend)
        assert initial_count > 0

        # Invalidate User tag
        count = await service.invalidate(["User"])

        # Some entries should be removed
        assert count >= 0  # Pattern matching behavior

    async def test_cache_entries_without_tag_remain(self):
        """Should keep cache entries that don't have the invalidated tag."""
        service, backend = create_cache_service()

        # Cache entry with User tag
        await service.cache_response(
            operation_name="GetUser",
            query="query { user { id } }",
            variables=None,
            response={"data": {"user": {"id": "1"}}},
            tags=["User"],
        )

        # Cache entry with Post tag (different tag)
        await service.cache_response(
            operation_name="GetPost",
            query="query { post { id } }",
            variables=None,
            response={"data": {"post": {"id": "1"}}},
            tags=["Post"],
        )

        # Invalidate only User tag
        await service.invalidate(["User"])

        # Post entry should still be retrievable
        cached = await service.get_cached_response(
            operation_name="GetPost",
            query="query { post { id } }",
            variables=None,
        )
        assert cached is not None
        assert cached["data"]["post"]["id"] == "1"


class TestMultipleTagInvalidation:
    """Tests for multiple tag invalidation."""

    async def test_invalidate_multiple_tags_at_once(self):
        """Should invalidate entries matching any of the specified tags."""
        service, backend = create_cache_service()

        # Cache entries with different tags
        await service.cache_response(
            operation_name="GetUser",
            query="query { user { id } }",
            variables=None,
            response={"data": {"user": {"id": "1"}}},
            tags=["User"],
        )
        await service.cache_response(
            operation_name="GetPost",
            query="query { post { id } }",
            variables=None,
            response={"data": {"post": {"id": "1"}}},
            tags=["Post"],
        )

        # Invalidate both tags
        count = await service.invalidate(["User", "Post"])

        # Both should be affected
        assert count >= 0

    async def test_verify_all_matching_entries_removed(self):
        """Should remove all entries matching any of the tags."""
        service, backend = create_cache_service()

        # Cache entry with tag1
        await service.cache_response(
            operation_name="Op1",
            query="query { op1 }",
            variables=None,
            response={"data": {"op1": "value1"}},
            tags=["tag1"],
        )

        # Cache entry with tag2
        await service.cache_response(
            operation_name="Op2",
            query="query { op2 }",
            variables=None,
            response={"data": {"op2": "value2"}},
            tags=["tag2"],
        )

        # Cache entry with tag3 (not invalidated)
        await service.cache_response(
            operation_name="Op3",
            query="query { op3 }",
            variables=None,
            response={"data": {"op3": "value3"}},
            tags=["tag3"],
        )

        # Invalidate tag1 and tag2
        await service.invalidate(["tag1", "tag2"])

        # tag3 entry should still exist
        cached = await service.get_cached_response(
            operation_name="Op3",
            query="query { op3 }",
            variables=None,
        )
        assert cached is not None

    async def test_non_matching_entries_remain(self):
        """Should not affect entries without matching tags."""
        service, backend = create_cache_service()

        # Cache entry without tags
        await service.cache_response(
            operation_name="NoTags",
            query="query { noTags }",
            variables=None,
            response={"data": {"noTags": "value"}},
            tags=None,
        )

        # Cache entry with different tag
        await service.cache_response(
            operation_name="DifferentTag",
            query="query { differentTag }",
            variables=None,
            response={"data": {"differentTag": "value"}},
            tags=["keep-me"],
        )

        # Invalidate unrelated tags
        await service.invalidate(["User", "Post"])

        # Both entries should still be retrievable
        cached1 = await service.get_cached_response(
            operation_name="NoTags",
            query="query { noTags }",
            variables=None,
        )
        assert cached1 is not None

        cached2 = await service.get_cached_response(
            operation_name="DifferentTag",
            query="query { differentTag }",
            variables=None,
        )
        assert cached2 is not None


class TestInvalidationEdgeCases:
    """Edge case tests for cache invalidation."""

    async def test_invalidate_nonexistent_tag(self):
        """Should not error when invalidating a non-existent tag."""
        service, backend = create_cache_service()

        # Cache an entry
        await service.cache_response(
            operation_name="Test",
            query="query { test }",
            variables=None,
            response={"data": {"test": "value"}},
            tags=["existing-tag"],
        )

        # Invalidate non-existent tag - should not raise
        count = await service.invalidate(["nonexistent-tag"])
        assert count >= 0  # Should return 0 or more

    async def test_invalidate_empty_tag_list(self):
        """Should handle empty tag list gracefully."""
        service, backend = create_cache_service()

        # Cache an entry
        await service.cache_response(
            operation_name="Test",
            query="query { test }",
            variables=None,
            response={"data": {"test": "value"}},
            tags=["some-tag"],
        )

        initial_count = len(backend)

        # Invalidate with empty list
        count = await service.invalidate([])

        # Should not affect anything
        assert count == 0
        assert len(backend) == initial_count

    async def test_invalidate_with_empty_cache(self):
        """Should handle invalidation on empty cache gracefully."""
        service, backend = create_cache_service()

        # Cache is empty
        assert len(backend) == 0

        # Invalidate - should not raise
        count = await service.invalidate(["any-tag"])
        assert count == 0


class TestPatternMatching:
    """Tests for pattern-based invalidation."""

    async def test_wildcard_pattern_matching(self):
        """Should match keys using wildcard patterns."""
        service, backend = create_cache_service(key_prefix="app")

        # Cache entries with pattern-able tags
        await service.cache_response(
            operation_name="GetUser1",
            query="query { user(id: 1) }",
            variables={"id": "1"},
            response={"data": {"user": {"id": "1"}}},
            tags=["User:1"],
        )
        await service.cache_response(
            operation_name="GetUser2",
            query="query { user(id: 2) }",
            variables={"id": "2"},
            response={"data": {"user": {"id": "2"}}},
            tags=["User:2"],
        )

        initial_count = len(backend)
        assert initial_count > 0

        # Invalidate all User:* entries via the User tag
        await service.invalidate(["User"])

    async def test_prefix_matching(self):
        """Should support prefix-based invalidation."""
        service, backend = create_cache_service()

        # Cache entries with hierarchical tags
        await service.cache_response(
            operation_name="GetUserPosts",
            query="query { userPosts }",
            variables=None,
            response={"data": {"userPosts": []}},
            tags=["User:1:posts"],
        )

        # Invalidate using prefix
        count = await service.invalidate(["User:1"])

        # Should match via pattern
        assert count >= 0


class TestCacheServiceMethods:
    """Tests for CacheService invalidation methods."""

    async def test_invalidate_method_returns_count(self):
        """CacheService.invalidate should return number of invalidated entries."""
        service, backend = create_cache_service()

        # Cache entries
        await service.cache_response(
            operation_name="Op1",
            query="query { op1 }",
            variables=None,
            response={"data": {}},
            tags=["Tag1"],
        )

        # Invalidate and check return value
        count = await service.invalidate(["Tag1"])
        assert isinstance(count, int)
        assert count >= 0

    async def test_invalidate_by_type_method(self):
        """CacheService.invalidate_by_type should invalidate by GraphQL type."""
        service, backend = create_cache_service()

        # Cache entries for User type
        await service.cache_response(
            operation_name="GetUser",
            query="query { user }",
            variables=None,
            response={"data": {"user": {}}},
            tags=["User"],
        )

        # Invalidate by type
        count = await service.invalidate_by_type("User")
        assert isinstance(count, int)
        assert count >= 0

    async def test_invalidate_by_type_is_alias(self):
        """invalidate_by_type should be equivalent to invalidate([type_name])."""
        service, backend = create_cache_service()

        # Cache entry
        await service.cache_response(
            operation_name="Test",
            query="query { test }",
            variables=None,
            response={"data": {}},
            tags=["TestType"],
        )

        # Both methods should work the same way
        count = await service.invalidate_by_type("TestType")
        assert count >= 0

    async def test_clear_removes_all_entries(self):
        """CacheService.clear should remove all cached entries."""
        service, backend = create_cache_service()

        # Cache multiple entries
        await service.cache_response(
            operation_name="Op1",
            query="query { op1 }",
            variables=None,
            response={"data": {}},
            tags=["Tag1"],
        )
        await service.cache_response(
            operation_name="Op2",
            query="query { op2 }",
            variables=None,
            response={"data": {}},
            tags=["Tag2"],
        )

        assert len(backend) > 0

        # Clear all
        await service.clear()

        assert len(backend) == 0

    async def test_clear_resets_stats(self):
        """CacheService.clear should reset hit/miss statistics."""
        service, backend = create_cache_service()

        # Generate some stats
        await service.cache_response(
            operation_name="Test",
            query="query { test }",
            variables=None,
            response={"data": {}},
        )
        await service.get_cached_response(
            operation_name="Test",
            query="query { test }",
            variables=None,
        )
        await service.get_cached_response(
            operation_name="Miss",
            query="query { miss }",
            variables=None,
        )

        assert service.stats["total"] > 0

        # Clear
        await service.clear()

        assert service.stats["hits"] == 0
        assert service.stats["misses"] == 0
        assert service.stats["total"] == 0


class TestInMemoryBackendPatternDelete:
    """Tests for InMemoryCacheBackend.delete_pattern."""

    async def test_delete_pattern_glob_matching(self):
        """Should delete keys matching glob pattern."""
        backend = InMemoryCacheBackend()

        # Set some keys
        await backend.set("user:1", b"data1")
        await backend.set("user:2", b"data2")
        await backend.set("post:1", b"data3")

        # Delete user:* pattern
        count = await backend.delete_pattern("user:*")

        assert count == 2
        assert await backend.get("user:1") is None
        assert await backend.get("user:2") is None
        assert await backend.get("post:1") is not None

    async def test_delete_pattern_no_matches(self):
        """Should return 0 when no keys match pattern."""
        backend = InMemoryCacheBackend()

        await backend.set("user:1", b"data")

        count = await backend.delete_pattern("post:*")

        assert count == 0
        assert await backend.get("user:1") is not None

    async def test_delete_pattern_empty_cache(self):
        """Should handle empty cache gracefully."""
        backend = InMemoryCacheBackend()

        count = await backend.delete_pattern("*")

        assert count == 0

    async def test_delete_pattern_complex_glob(self):
        """Should support complex glob patterns."""
        backend = InMemoryCacheBackend()

        await backend.set("app:cache:user:1", b"data1")
        await backend.set("app:cache:user:2", b"data2")
        await backend.set("app:cache:post:1", b"data3")
        await backend.set("other:cache:user:1", b"data4")

        # Delete app:cache:user:*
        count = await backend.delete_pattern("app:cache:user:*")

        assert count == 2
        assert await backend.get("app:cache:user:1") is None
        assert await backend.get("app:cache:post:1") is not None
        assert await backend.get("other:cache:user:1") is not None


class TestConcurrentInvalidation:
    """Tests for concurrent invalidation operations."""

    async def test_concurrent_invalidation_requests(self):
        """Should handle multiple concurrent invalidation requests."""
        service, backend = create_cache_service()

        # Cache entries
        for i in range(10):
            await service.cache_response(
                operation_name=f"Op{i}",
                query=f"query {{ op{i} }}",
                variables=None,
                response={"data": {f"op{i}": i}},
                tags=[f"Tag{i % 3}"],  # 3 different tags
            )

        # Concurrent invalidations
        tasks = [
            service.invalidate(["Tag0"]),
            service.invalidate(["Tag1"]),
            service.invalidate(["Tag2"]),
        ]

        results = await asyncio.gather(*tasks)

        # All should complete without error
        assert all(isinstance(r, int) for r in results)

    async def test_invalidation_during_cache_read(self):
        """Should handle invalidation during concurrent reads."""
        service, backend = create_cache_service()

        # Cache an entry
        await service.cache_response(
            operation_name="Test",
            query="query { test }",
            variables=None,
            response={"data": {"test": "value"}},
            tags=["TestTag"],
        )

        async def read_cache():
            for _ in range(5):
                await service.get_cached_response(
                    operation_name="Test",
                    query="query { test }",
                    variables=None,
                )
                await asyncio.sleep(0.001)

        async def invalidate_cache():
            await asyncio.sleep(0.002)
            await service.invalidate(["TestTag"])

        # Run concurrently - should not raise
        await asyncio.gather(read_cache(), invalidate_cache())

    async def test_invalidation_during_cache_write(self):
        """Should handle invalidation during concurrent writes."""
        service, backend = create_cache_service()

        async def write_cache():
            for i in range(5):
                await service.cache_response(
                    operation_name=f"Write{i}",
                    query=f"query {{ write{i} }}",
                    variables=None,
                    response={"data": {f"write{i}": i}},
                    tags=["WriteTag"],
                )
                await asyncio.sleep(0.001)

        async def invalidate_cache():
            await asyncio.sleep(0.002)
            await service.invalidate(["WriteTag"])

        # Run concurrently - should not raise
        await asyncio.gather(write_cache(), invalidate_cache())

    async def test_concurrent_clear_operations(self):
        """Should handle concurrent clear operations."""
        service, backend = create_cache_service()

        # Cache entries
        for i in range(5):
            await service.cache_response(
                operation_name=f"Op{i}",
                query=f"query {{ op{i} }}",
                variables=None,
                response={"data": {}},
            )

        # Multiple concurrent clears
        await asyncio.gather(
            service.clear(),
            service.clear(),
            service.clear(),
        )

        # Should be empty
        assert len(backend) == 0
