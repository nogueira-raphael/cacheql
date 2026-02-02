"""Tests for dynamic cache hints module."""

from unittest.mock import MagicMock

import pytest

from cacheql.core.entities.cache_control import CacheScope
from cacheql.core.services.cache_control_calculator import CacheControlContext
from cacheql.hints import (
    CACHE_CONTROL_CONTEXT_KEY,
    cache_hint,
    get_cache_control,
    inject_cache_control_context,
    no_cache,
    private_cache,
    public_cache,
    set_cache_hint,
)


class TestCacheHintHelper:
    """Tests for cache_hint helper function."""

    def test_cache_hint_basic(self) -> None:
        """Test creating basic cache hint."""
        hint = cache_hint(max_age=300)
        assert hint.max_age == 300
        assert hint.scope is None

    def test_cache_hint_with_scope(self) -> None:
        """Test creating cache hint with scope."""
        hint = cache_hint(max_age=60, scope="PRIVATE")
        assert hint.max_age == 60
        assert hint.scope == CacheScope.PRIVATE

    def test_cache_hint_with_scope_enum(self) -> None:
        """Test creating cache hint with scope enum."""
        hint = cache_hint(max_age=60, scope=CacheScope.PUBLIC)
        assert hint.scope == CacheScope.PUBLIC


class TestInjectCacheControlContext:
    """Tests for inject_cache_control_context."""

    def test_inject_context(self) -> None:
        """Test injecting cache control context."""
        context: dict = {}
        cache_control = CacheControlContext()

        inject_cache_control_context(context, cache_control)

        assert CACHE_CONTROL_CONTEXT_KEY in context
        assert context[CACHE_CONTROL_CONTEXT_KEY] is cache_control


class TestGetCacheControl:
    """Tests for get_cache_control."""

    def test_get_from_dict_context(self) -> None:
        """Test getting cache control from dict context."""
        cache_control = CacheControlContext()

        # Create mock info with dict context
        info = MagicMock()
        info.context = {CACHE_CONTROL_CONTEXT_KEY: cache_control}

        result = get_cache_control(info)
        assert result is cache_control

    def test_get_returns_none_when_not_available(self) -> None:
        """Test returns None when cache control not in context."""
        info = MagicMock()
        info.context = {}

        result = get_cache_control(info)
        assert result is None

    def test_get_returns_none_when_no_context(self) -> None:
        """Test returns None when info has no context."""
        info = MagicMock(spec=[])  # No context attribute

        result = get_cache_control(info)
        assert result is None


class TestSetCacheHint:
    """Tests for set_cache_hint."""

    def test_set_hint_success(self) -> None:
        """Test setting cache hint successfully."""
        cache_control = CacheControlContext()
        cache_control._current_path = ["users"]

        info = MagicMock()
        info.context = {CACHE_CONTROL_CONTEXT_KEY: cache_control}

        result = set_cache_hint(info, max_age=300, scope="PRIVATE")

        assert result is True
        assert len(cache_control.resolver_hints) == 1
        hint = cache_control.resolver_hints[0]
        assert hint.hint.max_age == 300
        assert hint.hint.scope == CacheScope.PRIVATE

    def test_set_hint_no_cache_control(self) -> None:
        """Test setting hint when cache control not available."""
        info = MagicMock()
        info.context = {}

        result = set_cache_hint(info, max_age=300)

        assert result is False


class TestNoCacheHelper:
    """Tests for no_cache helper."""

    def test_no_cache_sets_max_age_zero(self) -> None:
        """Test no_cache sets maxAge to 0."""
        cache_control = CacheControlContext()
        cache_control._current_path = ["sensitive"]

        info = MagicMock()
        info.context = {CACHE_CONTROL_CONTEXT_KEY: cache_control}

        result = no_cache(info)

        assert result is True
        assert cache_control.resolver_hints[0].hint.max_age == 0


class TestPrivateCacheHelper:
    """Tests for private_cache helper."""

    def test_private_cache(self) -> None:
        """Test private_cache sets PRIVATE scope."""
        cache_control = CacheControlContext()

        info = MagicMock()
        info.context = {CACHE_CONTROL_CONTEXT_KEY: cache_control}

        result = private_cache(info, max_age=300)

        assert result is True
        hint = cache_control.resolver_hints[0].hint
        assert hint.max_age == 300
        assert hint.scope == CacheScope.PRIVATE


class TestPublicCacheHelper:
    """Tests for public_cache helper."""

    def test_public_cache(self) -> None:
        """Test public_cache sets PUBLIC scope."""
        cache_control = CacheControlContext()

        info = MagicMock()
        info.context = {CACHE_CONTROL_CONTEXT_KEY: cache_control}

        result = public_cache(info, max_age=3600)

        assert result is True
        hint = cache_control.resolver_hints[0].hint
        assert hint.max_age == 3600
        assert hint.scope == CacheScope.PUBLIC
