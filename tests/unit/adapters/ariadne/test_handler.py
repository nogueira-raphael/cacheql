"""Unit tests for CachingGraphQLHTTPHandler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ariadne = pytest.importorskip("ariadne")

from cacheql.adapters.ariadne.handler import CachingGraphQLHTTPHandler  # noqa: E402
from cacheql.core.entities.cache_control import (  # noqa: E402
    CacheScope,
    ResponseCachePolicy,
)


def _make_handler(
    session_id=None,
    default_max_age: int = 300,
) -> CachingGraphQLHTTPHandler:
    """Create a handler with a mock cache service."""
    from cacheql.core.entities.cache_config import CacheConfig

    svc = MagicMock()
    svc.config = CacheConfig(default_max_age=default_max_age)
    svc.get_cached_response = AsyncMock(return_value=None)
    svc.cache_response = AsyncMock()

    handler = object.__new__(CachingGraphQLHTTPHandler)
    handler._cache_service = svc
    handler._should_cache = None
    handler._session_id = session_id
    handler._set_http_headers = True
    handler._debug = False
    handler._schema_directives = None

    # Mock calculator
    handler._calculator = MagicMock()
    handler._calculator.calculate_policy.return_value = ResponseCachePolicy(
        max_age=300, scope=CacheScope.PUBLIC
    )

    return handler


class TestGetSessionId:
    def test_callback_returns_value(self):
        handler = _make_handler(session_id=lambda ctx: "user-42")
        assert handler._get_session_id({"current_user_id": "42"}) == "user-42"

    def test_callback_returns_none(self):
        handler = _make_handler(session_id=lambda ctx: None)
        assert handler._get_session_id({"current_user_id": "42"}) is None

    def test_no_callback(self):
        handler = _make_handler(session_id=None)
        assert handler._get_session_id({"current_user_id": "42"}) is None


class TestDualLookup:
    @pytest.mark.asyncio
    async def test_private_hit(self):
        """When sid is set and private cache entry exists, return it."""
        handler = _make_handler(session_id=lambda ctx: "user-1")
        private_response = {"data": {"me": {"id": "1"}}}
        handler._cache_service.get_cached_response = AsyncMock(
            side_effect=[private_response]
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { me { id } }"}

        success, result = await handler.execute_graphql_query(
            request, data, context_value={"current_user_id": "1"}
        )

        assert success is True
        assert result == private_response
        handler._cache_service.get_cached_response.assert_awaited_once_with(
            operation_name=None,
            query="query { me { id } }",
            variables=None,
            context={"session_id": "user-1"},
        )

    @pytest.mark.asyncio
    async def test_public_hit_after_private_miss(self):
        """When sid is set but private misses, try public key."""
        handler = _make_handler(session_id=lambda ctx: "user-1")
        public_response = {"data": {"users": [{"id": "1"}]}}
        handler._cache_service.get_cached_response = AsyncMock(
            side_effect=[None, public_response]
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { users { id } }"}

        success, result = await handler.execute_graphql_query(
            request, data, context_value={"current_user_id": "1"}
        )

        assert success is True
        assert result == public_response
        calls = handler._cache_service.get_cached_response.call_args_list
        assert len(calls) == 2
        # First call: private lookup
        assert calls[0].kwargs["context"] == {"session_id": "user-1"}
        # Second call: public lookup
        assert calls[1].kwargs["context"] is None

    @pytest.mark.asyncio
    async def test_both_miss(self):
        """When both private and public miss, execute query."""
        handler = _make_handler(session_id=lambda ctx: "user-1")
        handler._cache_service.get_cached_response = AsyncMock(
            side_effect=[None, None]
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { users { id } }"}
        executed_response = (True, {"data": {"users": []}})

        with patch.object(
            CachingGraphQLHTTPHandler.__bases__[0],
            "execute_graphql_query",
            new_callable=AsyncMock,
            return_value=executed_response,
        ):
            success, result = await handler.execute_graphql_query(
                request, data, context_value={"current_user_id": "1"}
            )

        assert success is True
        assert handler._cache_service.get_cached_response.await_count == 2

    @pytest.mark.asyncio
    async def test_no_sid_skips_private_lookup(self):
        """When no session_id callback, only public lookup is performed."""
        handler = _make_handler(session_id=None)
        public_response = {"data": {"users": [{"id": "1"}]}}
        handler._cache_service.get_cached_response = AsyncMock(
            return_value=public_response
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { users { id } }"}

        success, result = await handler.execute_graphql_query(
            request, data, context_value={}
        )

        assert success is True
        assert result == public_response
        handler._cache_service.get_cached_response.assert_awaited_once_with(
            operation_name=None,
            query="query { users { id } }",
            variables=None,
            context=None,
        )

    @pytest.mark.asyncio
    async def test_sid_callback_returns_none_skips_private_lookup(self):
        """When session_id callback returns None, only public lookup."""
        handler = _make_handler(session_id=lambda ctx: None)
        public_response = {"data": {"users": [{"id": "1"}]}}
        handler._cache_service.get_cached_response = AsyncMock(
            return_value=public_response
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { users { id } }"}

        success, result = await handler.execute_graphql_query(
            request, data, context_value={}
        )

        assert success is True
        handler._cache_service.get_cached_response.assert_awaited_once_with(
            operation_name=None,
            query="query { users { id } }",
            variables=None,
            context=None,
        )


class TestScopeAwareStore:
    @pytest.mark.asyncio
    async def test_public_scope_stores_with_no_context(self):
        handler = _make_handler(session_id=lambda ctx: "user-1")
        handler._cache_service.get_cached_response = AsyncMock(
            side_effect=[None, None]
        )
        handler._calculator.calculate_policy.return_value = ResponseCachePolicy(
            max_age=300, scope=CacheScope.PUBLIC
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { users { id } }"}
        executed_response = (True, {"data": {"users": []}})

        with patch.object(
            CachingGraphQLHTTPHandler.__bases__[0],
            "execute_graphql_query",
            new_callable=AsyncMock,
            return_value=executed_response,
        ):
            await handler.execute_graphql_query(
                request, data, context_value={"current_user_id": "1"}
            )

        handler._cache_service.cache_response.assert_awaited_once()
        call_kwargs = handler._cache_service.cache_response.call_args.kwargs
        assert call_kwargs["context"] is None

    @pytest.mark.asyncio
    async def test_private_scope_with_sid_stores_with_session_context(self):
        handler = _make_handler(session_id=lambda ctx: "user-1")
        handler._cache_service.get_cached_response = AsyncMock(
            side_effect=[None, None]
        )
        handler._calculator.calculate_policy.return_value = ResponseCachePolicy(
            max_age=300, scope=CacheScope.PRIVATE
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { me { id } }"}
        executed_response = (True, {"data": {"me": {"id": "1"}}})

        with patch.object(
            CachingGraphQLHTTPHandler.__bases__[0],
            "execute_graphql_query",
            new_callable=AsyncMock,
            return_value=executed_response,
        ):
            await handler.execute_graphql_query(
                request, data, context_value={"current_user_id": "1"}
            )

        handler._cache_service.cache_response.assert_awaited_once()
        call_kwargs = handler._cache_service.cache_response.call_args.kwargs
        assert call_kwargs["context"] == {"session_id": "user-1"}

    @pytest.mark.asyncio
    async def test_private_scope_without_sid_skips_cache(self):
        handler = _make_handler(session_id=None)
        handler._cache_service.get_cached_response = AsyncMock(return_value=None)
        handler._calculator.calculate_policy.return_value = ResponseCachePolicy(
            max_age=300, scope=CacheScope.PRIVATE
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { me { id } }"}
        executed_response = (True, {"data": {"me": {"id": "1"}}})

        with patch.object(
            CachingGraphQLHTTPHandler.__bases__[0],
            "execute_graphql_query",
            new_callable=AsyncMock,
            return_value=executed_response,
        ):
            await handler.execute_graphql_query(
                request, data, context_value={}
            )

        handler._cache_service.cache_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_private_scope_with_sid_callback_returning_none_skips_cache(self):
        handler = _make_handler(session_id=lambda ctx: None)
        handler._cache_service.get_cached_response = AsyncMock(return_value=None)
        handler._calculator.calculate_policy.return_value = ResponseCachePolicy(
            max_age=300, scope=CacheScope.PRIVATE
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { me { id } }"}
        executed_response = (True, {"data": {"me": {"id": "1"}}})

        with patch.object(
            CachingGraphQLHTTPHandler.__bases__[0],
            "execute_graphql_query",
            new_callable=AsyncMock,
            return_value=executed_response,
        ):
            await handler.execute_graphql_query(
                request, data, context_value={}
            )

        handler._cache_service.cache_response.assert_not_called()

    @pytest.mark.asyncio
    async def test_not_cacheable_skips_store(self):
        handler = _make_handler(session_id=lambda ctx: "user-1")
        handler._cache_service.get_cached_response = AsyncMock(
            side_effect=[None, None]
        )
        handler._calculator.calculate_policy.return_value = ResponseCachePolicy(
            max_age=0, scope=CacheScope.PUBLIC
        )

        request = MagicMock()
        request.state = MagicMock()
        data = {"query": "query { users { id } }"}
        executed_response = (True, {"data": {"users": []}})

        with patch.object(
            CachingGraphQLHTTPHandler.__bases__[0],
            "execute_graphql_query",
            new_callable=AsyncMock,
            return_value=executed_response,
        ):
            await handler.execute_graphql_query(
                request, data, context_value={}
            )

        handler._cache_service.cache_response.assert_not_called()
