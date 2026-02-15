"""Unit tests for Ariadne decorators."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from cacheql.adapters.ariadne import decorators
from cacheql.adapters.ariadne.decorators import (
    _build_cache_key,
    _get_type_name_from_func,
    _interpolate_string,
    _resolve_tags,
    cached_resolver,
    configure_cache,
    invalidates_cache,
)
from cacheql.core.entities.cache_config import CacheConfig


def _make_cache_service(
    config: CacheConfig | None = None,
    cached_data: bytes | None = None,
) -> MagicMock:
    """Create a mock CacheService."""
    svc = MagicMock()
    svc.config = config or CacheConfig()
    svc._backend = MagicMock()
    svc._backend.get = AsyncMock(return_value=cached_data)
    svc._backend.set = AsyncMock()
    svc._serializer = MagicMock()
    svc._serializer.serialize.return_value = b'{"serialized": true}'
    svc._serializer.deserialize.return_value = {"deserialized": True}
    svc.invalidate = AsyncMock(return_value=0)
    return svc


@pytest.fixture(autouse=True)
def _reset_globals():
    """Reset module-level globals before and after each test."""
    decorators._cache_service = None
    decorators._key_builder = None
    yield
    decorators._cache_service = None
    decorators._key_builder = None


# ── configure_cache ──────────────────────────────────────────────────────


class TestConfigureCache:
    def test_sets_global_cache_service(self):
        svc = _make_cache_service()

        configure_cache(svc)

        assert decorators._cache_service is svc

    def test_sets_global_key_builder_with_prefix(self):
        config = CacheConfig(key_prefix="myapp")
        svc = _make_cache_service(config=config)

        configure_cache(svc)

        assert decorators._key_builder is not None
        assert decorators._key_builder._prefix == "myapp"


# ── cached_resolver ──────────────────────────────────────────────────────


class TestCachedResolver:
    async def test_no_cache_configured_executes_directly(self):
        resolver = AsyncMock(return_value={"id": "1"})
        decorated = cached_resolver()(resolver)

        result = await decorated("root", "info")

        assert result == {"id": "1"}
        resolver.assert_awaited_once_with("root", "info")

    async def test_cache_miss_executes_and_caches(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value={"id": "1", "name": "Alice"})
        decorated = cached_resolver()(resolver)
        resolver.__name__ = "resolve_user"

        result = await decorated("root", "info")

        assert result == {"id": "1", "name": "Alice"}
        resolver.assert_awaited_once()
        svc._backend.set.assert_awaited()
        svc._serializer.serialize.assert_called_once_with({"id": "1", "name": "Alice"})

    async def test_cache_hit_returns_cached_without_executing(self):
        svc = _make_cache_service(cached_data=b'{"id": "1"}')
        configure_cache(svc)

        resolver = AsyncMock(return_value={"id": "1"})
        decorated = cached_resolver()(resolver)
        resolver.__name__ = "resolve_user"

        result = await decorated("root", "info")

        assert result == {"deserialized": True}
        resolver.assert_not_awaited()
        svc._serializer.deserialize.assert_called_once_with(b'{"id": "1"}')

    async def test_custom_ttl_is_used(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_item"
        decorated = cached_resolver(ttl=timedelta(seconds=30))(resolver)

        await decorated("root", "info")

        set_call = svc._backend.set.call_args
        assert set_call[0][2] == timedelta(seconds=30)

    async def test_default_ttl_used_when_no_custom_ttl(self):
        config = CacheConfig(default_ttl=timedelta(minutes=10))
        svc = _make_cache_service(config=config, cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_item"
        decorated = cached_resolver()(resolver)

        await decorated("root", "info")

        set_call = svc._backend.set.call_args
        assert set_call[0][2] == timedelta(minutes=10)

    async def test_tags_are_stored(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_user"
        decorated = cached_resolver(tags=["User"])(resolver)

        await decorated("root", "info")

        # backend.set is called once for data + once per tag
        assert svc._backend.set.await_count == 2

    async def test_tags_with_interpolation(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_user"
        decorated = cached_resolver(tags=["User", "User:{id}"])(resolver)

        await decorated("root", "info", id="42")

        # data + 2 tags = 3 set calls
        assert svc._backend.set.await_count == 3
        tag_calls = svc._backend.set.call_args_list
        # Second call should be for "User" tag, third for "User:42"
        tag_key_2 = tag_calls[1][0][0]
        tag_key_3 = tag_calls[2][0][0]
        assert ":tag:User:" in tag_key_2
        assert ":tag:User:42:" in tag_key_3

    async def test_custom_key_as_string(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_user"
        decorated = cached_resolver(key="user:{id}")(resolver)

        await decorated("root", "info", id="99")

        get_call = svc._backend.get.call_args[0][0]
        assert get_call == "user:99"

    async def test_custom_key_as_callable(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_user"
        key_fn = MagicMock(return_value="custom-key-123")
        decorated = cached_resolver(key=key_fn)(resolver)

        await decorated("root", "info", id="5")

        key_fn.assert_called_once_with("root", "info", id="5")
        get_call = svc._backend.get.call_args[0][0]
        assert get_call == "custom-key-123"

    async def test_preserves_function_name(self):
        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_user"
        resolver.__qualname__ = "resolve_user"
        decorated = cached_resolver()(resolver)

        assert decorated.__name__ == "resolve_user"

    async def test_no_tags_skips_tag_storage(self):
        svc = _make_cache_service(cached_data=None)
        configure_cache(svc)

        resolver = AsyncMock(return_value="data")
        resolver.__name__ = "resolve_item"
        decorated = cached_resolver(tags=None)(resolver)

        await decorated("root", "info")

        # Only one set call for data, no tag calls
        assert svc._backend.set.await_count == 1


# ── invalidates_cache ────────────────────────────────────────────────────


class TestInvalidatesCache:
    async def test_executes_mutation_and_invalidates(self):
        svc = _make_cache_service()
        configure_cache(svc)

        mutation = AsyncMock(return_value={"id": "1", "name": "Updated"})
        decorated = invalidates_cache(tags=["User"])(mutation)

        result = await decorated("root", "info")

        assert result == {"id": "1", "name": "Updated"}
        mutation.assert_awaited_once_with("root", "info")
        svc.invalidate.assert_awaited_once_with(["User"])

    async def test_no_cache_configured_executes_without_error(self):
        mutation = AsyncMock(return_value={"ok": True})
        decorated = invalidates_cache(tags=["User"])(mutation)

        result = await decorated("root", "info")

        assert result == {"ok": True}
        mutation.assert_awaited_once()

    async def test_no_tags_skips_invalidation(self):
        svc = _make_cache_service()
        configure_cache(svc)

        mutation = AsyncMock(return_value={"ok": True})
        decorated = invalidates_cache(tags=None)(mutation)

        result = await decorated("root", "info")

        assert result == {"ok": True}
        svc.invalidate.assert_not_called()

    async def test_tags_with_interpolation(self):
        svc = _make_cache_service()
        configure_cache(svc)

        mutation = AsyncMock(return_value={"ok": True})
        decorated = invalidates_cache(tags=["User:{id}"])(mutation)

        await decorated("root", "info", id="42")

        svc.invalidate.assert_awaited_once_with(["User:42"])

    async def test_preserves_function_name(self):
        mutation = AsyncMock(return_value={"ok": True})
        mutation.__name__ = "resolve_update_user"
        mutation.__qualname__ = "resolve_update_user"
        decorated = invalidates_cache(tags=["User"])(mutation)

        assert decorated.__name__ == "resolve_update_user"


# ── _build_cache_key ─────────────────────────────────────────────────────


class TestBuildCacheKey:
    def test_raises_when_key_builder_not_configured(self):
        def my_func():
            pass

        with pytest.raises(RuntimeError, match="Cache not configured"):
            _build_cache_key(my_func, (), {}, None)

    def test_callable_custom_key(self):
        svc = _make_cache_service()
        configure_cache(svc)

        key_fn = MagicMock(return_value="my-custom-key")

        result = _build_cache_key(lambda: None, ("a", "b"), {"x": 1}, key_fn)

        key_fn.assert_called_once_with("a", "b", x=1)
        assert result == "my-custom-key"

    def test_string_custom_key_with_interpolation(self):
        svc = _make_cache_service()
        configure_cache(svc)

        result = _build_cache_key(lambda: None, (), {"id": "42"}, "user:{id}")

        assert result == "user:42"

    def test_default_key_uses_function_name(self):
        svc = _make_cache_service()
        configure_cache(svc)

        def resolve_user():
            pass

        result = _build_cache_key(resolve_user, (), {}, None)

        assert "resolve_user" in result
        assert "Query" in result

    def test_default_key_includes_kwargs(self):
        svc = _make_cache_service()
        configure_cache(svc)

        def resolve_user():
            pass

        key_no_args = _build_cache_key(resolve_user, (), {}, None)
        key_with_args = _build_cache_key(resolve_user, (), {"id": "1"}, None)

        assert key_no_args != key_with_args

    def test_default_key_includes_parent_value(self):
        svc = _make_cache_service()
        configure_cache(svc)

        def resolve_user():
            pass

        key_no_parent = _build_cache_key(resolve_user, (), {}, None)
        key_with_parent = _build_cache_key(resolve_user, ({"id": "1"},), {}, None)

        assert key_no_parent != key_with_parent


# ── _get_type_name_from_func ─────────────────────────────────────────────


class TestGetTypeNameFromFunc:
    def test_returns_graphql_type_attribute(self):
        def my_func():
            pass

        my_func._graphql_type = "User"

        assert _get_type_name_from_func(my_func) == "User"

    def test_resolve_prefix_returns_query(self):
        def resolve_user():
            pass

        assert _get_type_name_from_func(resolve_user) == "Query"

    def test_no_prefix_returns_query(self):
        def get_user():
            pass

        assert _get_type_name_from_func(get_user) == "Query"


# ── _resolve_tags ────────────────────────────────────────────────────────


class TestResolveTags:
    def test_none_tags_returns_empty(self):
        assert _resolve_tags(None, (), {}) == []

    def test_empty_tags_returns_empty(self):
        assert _resolve_tags([], (), {}) == []

    def test_tags_without_placeholders(self):
        result = _resolve_tags(["User", "Post"], (), {})
        assert result == ["User", "Post"]

    def test_tags_with_interpolation(self):
        result = _resolve_tags(["User:{id}"], (), {"id": "42"})
        assert result == ["User:42"]

    def test_multiple_tags_mixed(self):
        result = _resolve_tags(["User", "User:{id}"], (), {"id": "5"})
        assert result == ["User", "User:5"]


# ── _interpolate_string ─────────────────────────────────────────────────


class TestInterpolateString:
    def test_replaces_placeholder_with_kwarg(self):
        result = _interpolate_string("User:{id}", (), {"id": "42"})
        assert result == "User:42"

    def test_keeps_placeholder_if_not_in_kwargs(self):
        result = _interpolate_string("User:{id}", (), {})
        assert result == "User:{id}"

    def test_multiple_placeholders(self):
        result = _interpolate_string(
            "{type}:{id}", (), {"type": "User", "id": "1"}
        )
        assert result == "User:1"

    def test_no_placeholders(self):
        result = _interpolate_string("plain-string", (), {})
        assert result == "plain-string"

    def test_partial_match(self):
        result = _interpolate_string(
            "{found}:{missing}", (), {"found": "yes"}
        )
        assert result == "yes:{missing}"
