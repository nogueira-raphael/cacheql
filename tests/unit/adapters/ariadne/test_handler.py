"""Unit tests for CachingGraphQLHTTPHandler._extract_session_context."""

from unittest.mock import MagicMock

import pytest

ariadne = pytest.importorskip("ariadne")

from cacheql.adapters.ariadne.handler import CachingGraphQLHTTPHandler  # noqa: E402
from cacheql.core.entities.cache_config import CacheConfig  # noqa: E402


def _make_handler(config: CacheConfig | None = None) -> CachingGraphQLHTTPHandler:
    """Create a handler with a mock cache service."""
    svc = MagicMock()
    svc.config = config or CacheConfig()

    handler = object.__new__(CachingGraphQLHTTPHandler)
    handler._cache_service = svc
    return handler


class TestExtractSessionContext:
    def test_returns_none_when_no_session_context_keys(self):
        handler = _make_handler(CacheConfig(session_context_keys=None))
        result = handler._extract_session_context({"current_user_id": "1"})
        assert result is None

    def test_returns_none_when_empty_session_context_keys(self):
        handler = _make_handler(CacheConfig(session_context_keys=[]))
        result = handler._extract_session_context({"current_user_id": "1"})
        assert result is None

    def test_returns_none_when_context_is_not_dict(self):
        handler = _make_handler(
            CacheConfig(session_context_keys=["current_user_id"])
        )
        result = handler._extract_session_context("not-a-dict")
        assert result is None

    def test_returns_none_when_context_is_none(self):
        handler = _make_handler(
            CacheConfig(session_context_keys=["current_user_id"])
        )
        result = handler._extract_session_context(None)
        assert result is None

    def test_extracts_configured_keys(self):
        handler = _make_handler(
            CacheConfig(session_context_keys=["current_user_id"])
        )
        result = handler._extract_session_context(
            {"current_user_id": "42", "request": "obj"}
        )
        assert result == {"current_user_id": "42"}

    def test_extracts_multiple_keys(self):
        handler = _make_handler(
            CacheConfig(session_context_keys=["current_user_id", "tenant_id"])
        )
        result = handler._extract_session_context(
            {"current_user_id": "42", "tenant_id": "t1", "extra": "ignored"}
        )
        assert result == {"current_user_id": "42", "tenant_id": "t1"}

    def test_returns_none_when_no_configured_keys_found(self):
        handler = _make_handler(
            CacheConfig(session_context_keys=["current_user_id"])
        )
        result = handler._extract_session_context({"other_key": "value"})
        assert result is None

    def test_partial_match_returns_found_keys_only(self):
        handler = _make_handler(
            CacheConfig(session_context_keys=["current_user_id", "tenant_id"])
        )
        result = handler._extract_session_context({"current_user_id": "42"})
        assert result == {"current_user_id": "42"}
