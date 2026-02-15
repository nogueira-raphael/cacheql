"""Unit tests for Strawberry CacheExtension."""

import contextlib
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

strawberry = pytest.importorskip("strawberry")

from strawberry.extensions import SchemaExtension  # noqa: E402

from cacheql.adapters.strawberry.extension import CacheExtension  # noqa: E402
from cacheql.core.entities.cache_config import CacheConfig  # noqa: E402


def _make_cache_service(
    config: CacheConfig | None = None,
    cached_response: object | None = None,
) -> MagicMock:
    """Create a mock CacheService."""
    svc = MagicMock()
    svc.config = config or CacheConfig()
    svc.stats = {"hits": 0, "misses": 0, "total": 0}
    svc.get_cached_response = AsyncMock(return_value=cached_response)
    svc.cache_response = AsyncMock()
    svc.invalidate = AsyncMock(return_value=0)
    return svc


def _make_context(**overrides: object) -> MagicMock:
    """Create a mock ExecutionContext with standard attributes."""
    defaults = {
        "query": "query GetUser { user { id } }",
        "variables": {"id": "1"},
        "operation_name": "GetUser",
        "operation_type": None,
        "result": None,
        "context": {},
    }
    defaults.update(overrides)

    ctx = MagicMock()
    for attr, value in defaults.items():
        setattr(ctx, attr, value)

    return ctx


def _make_ext(
    cache_service: MagicMock,
    ctx: MagicMock,
    should_cache: object | None = None,
) -> object:
    """Instantiate the inner _CacheExtension with a mocked execution_context."""
    cls = CacheExtension(cache_service, should_cache=should_cache)
    with patch.object(SchemaExtension, "__init__", return_value=None):
        ext = cls(execution_context=ctx)
    ext.execution_context = ctx
    return ext


async def _drive_async_gen(gen):
    """Drive an async generator: advance past yield, then close."""
    await gen.__anext__()
    with contextlib.suppress(StopAsyncIteration):
        await gen.__anext__()


# ── Factory ──────────────────────────────────────────────────────────────


class TestCacheExtensionFactory:
    def test_returns_schema_extension_subclass(self):
        svc = _make_cache_service()
        cls = CacheExtension(svc)
        assert issubclass(cls, SchemaExtension)

    def test_accepts_should_cache_callback(self):
        svc = _make_cache_service()
        cls = CacheExtension(svc, should_cache=lambda ctx: True)
        assert issubclass(cls, SchemaExtension)

    def test_works_with_default_should_cache_none(self):
        svc = _make_cache_service()
        cls = CacheExtension(svc, should_cache=None)
        assert issubclass(cls, SchemaExtension)


# ── _check_cache ─────────────────────────────────────────────────────────


class TestCheckCache:
    async def test_no_query_returns_early(self):
        svc = _make_cache_service()
        ctx = _make_context(query=None)
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_not_called()

    async def test_empty_query_returns_early(self):
        svc = _make_cache_service()
        ctx = _make_context(query="")
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_not_called()

    async def test_extracts_variables_and_operation_name(self):
        svc = _make_cache_service()
        ctx = _make_context(variables={"x": 1}, operation_name="Op")
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_awaited_once_with(
            operation_name="Op",
            query=ctx.query,
            variables={"x": 1},
            context=None,
        )

    async def test_missing_variables_defaults_to_none(self):
        svc = _make_cache_service()
        ctx = _make_context()
        del ctx.variables
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        call_kwargs = svc.get_cached_response.call_args.kwargs
        assert call_kwargs["variables"] is None

    async def test_missing_operation_name_defaults_to_none(self):
        svc = _make_cache_service()
        ctx = _make_context()
        del ctx.operation_name
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        call_kwargs = svc.get_cached_response.call_args.kwargs
        assert call_kwargs["operation_name"] is None

    async def test_detects_mutation_via_operation_type(self):
        svc = _make_cache_service()
        ctx = _make_context(operation_type="MUTATION")
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._is_mutation is True

    async def test_detects_query_via_operation_type(self):
        svc = _make_cache_service()
        ctx = _make_context(operation_type="QUERY")
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._is_mutation is False

    async def test_falls_back_to_query_text_when_operation_type_is_none(self):
        svc = _make_cache_service()
        ctx = _make_context(
            query="mutation CreateUser { createUser { id } }",
            operation_type=None,
        )
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._is_mutation is True

    async def test_falls_back_to_query_text_on_runtime_error(self):
        svc = _make_cache_service()
        ctx = _make_context(query="mutation Foo { foo }")
        type(ctx).operation_type = PropertyMock(side_effect=RuntimeError)
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._is_mutation is True

    async def test_query_text_detection_case_insensitive(self):
        svc = _make_cache_service()
        ctx = _make_context(
            query="  MUTATION CreateUser { createUser { id } }",
            operation_type=None,
        )
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._is_mutation is True

    async def test_mutation_skipped_when_cache_mutations_false(self):
        config = CacheConfig(cache_mutations=False)
        svc = _make_cache_service(config=config)
        ctx = _make_context(
            query="mutation Foo { foo }",
            operation_type="MUTATION",
        )
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_not_called()

    async def test_should_cache_returning_false_skips_lookup(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx, should_cache=lambda c: False)

        await ext._check_cache()

        svc.get_cached_response.assert_not_called()

    async def test_should_cache_none_proceeds(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx, should_cache=None)

        await ext._check_cache()

        svc.get_cached_response.assert_awaited_once()

    async def test_cache_hit_sets_cached_response_and_context_key(self):
        cached_data = {"user": {"id": "1"}}
        svc = _make_cache_service(cached_response=cached_data)
        ctx = _make_context(context={})
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._cached_response == cached_data
        assert ctx.context["_cacheql_cached_response"] == cached_data

    async def test_cache_hit_no_context_attr_no_error(self):
        cached_data = {"user": {"id": "1"}}
        svc = _make_cache_service(cached_response=cached_data)
        ctx = _make_context(context=None)
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._cached_response == cached_data

    async def test_cache_miss_leaves_cached_response_none(self):
        svc = _make_cache_service(cached_response=None)
        ctx = _make_context()
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        assert ext._cached_response is None


# ── on_execute ───────────────────────────────────────────────────────────


class TestOnExecute:
    async def test_no_cached_response_yields_without_modifying_result(self):
        svc = _make_cache_service()
        ctx = _make_context(result=MagicMock())
        ext = _make_ext(svc, ctx)
        original_result = ctx.result

        await _drive_async_gen(ext.on_execute())

        assert ctx.result is original_result

    async def test_cached_response_sets_execution_result(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx)
        ext._cached_response = {"user": {"id": "1"}}

        await _drive_async_gen(ext.on_execute())

        assert ctx.result.data == {"user": {"id": "1"}}
        assert ctx.result.errors == []

    async def test_cached_result_has_empty_errors_list(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx)
        ext._cached_response = {"data": "value"}

        await _drive_async_gen(ext.on_execute())

        assert ctx.result.errors == []


# ── _cache_response ──────────────────────────────────────────────────────


class TestCacheResponse:
    async def test_already_cached_returns_early(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx)
        ext._cached_response = {"already": "cached"}

        await ext._cache_response()

        svc.cache_response.assert_not_called()

    async def test_mutation_no_cache_with_auto_invalidate(self):
        config = CacheConfig(cache_mutations=False, auto_invalidate_on_mutation=True)
        svc = _make_cache_service(config=config)
        result = MagicMock()
        result.data = {"createUser": {"__typename": "User", "id": "1"}}
        result.errors = None
        ctx = _make_context(result=result)
        ext = _make_ext(svc, ctx)
        ext._is_mutation = True

        await ext._cache_response()

        svc.invalidate.assert_awaited_once()
        svc.cache_response.assert_not_called()

    async def test_mutation_no_cache_no_auto_invalidate(self):
        config = CacheConfig(cache_mutations=False, auto_invalidate_on_mutation=False)
        svc = _make_cache_service(config=config)
        ctx = _make_context()
        ext = _make_ext(svc, ctx)
        ext._is_mutation = True

        await ext._cache_response()

        svc.invalidate.assert_not_called()
        svc.cache_response.assert_not_called()

    async def test_no_result_returns_early(self):
        svc = _make_cache_service()
        ctx = _make_context(result=None)
        ext = _make_ext(svc, ctx)

        await ext._cache_response()

        svc.cache_response.assert_not_called()

    async def test_result_with_errors_returns_early(self):
        svc = _make_cache_service()
        result = MagicMock()
        result.errors = [MagicMock()]
        ctx = _make_context(result=result)
        ext = _make_ext(svc, ctx)

        await ext._cache_response()

        svc.cache_response.assert_not_called()

    async def test_no_query_returns_early(self):
        svc = _make_cache_service()
        result = MagicMock()
        result.errors = None
        ctx = _make_context(query=None, result=result)
        ext = _make_ext(svc, ctx)

        await ext._cache_response()

        svc.cache_response.assert_not_called()

    async def test_success_calls_cache_response(self):
        svc = _make_cache_service()
        result = MagicMock()
        result.errors = None
        result.data = {"user": {"id": "1"}}
        ctx = _make_context(
            query="query GetUser { user { id } }",
            variables={"id": "1"},
            operation_name="GetUser",
            result=result,
        )
        ext = _make_ext(svc, ctx)

        await ext._cache_response()

        svc.cache_response.assert_awaited_once_with(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables={"id": "1"},
            response={"user": {"id": "1"}},
            context=None,
        )

    async def test_result_without_data_attr_uses_result_itself(self):
        svc = _make_cache_service()
        result = MagicMock(spec=[])  # no attributes at all
        result.errors = None
        # Remove "data" from spec so hasattr returns False
        ctx = _make_context(result=result)
        ext = _make_ext(svc, ctx)

        await ext._cache_response()

        call_kwargs = svc.cache_response.call_args.kwargs
        assert call_kwargs["response"] is result


# ── _handle_mutation_invalidation ────────────────────────────────────────


class TestHandleMutationInvalidation:
    async def test_no_result_returns_early(self):
        svc = _make_cache_service()
        ctx = _make_context(result=None)
        ext = _make_ext(svc, ctx)

        await ext._handle_mutation_invalidation()

        svc.invalidate.assert_not_called()

    async def test_no_data_returns_early(self):
        svc = _make_cache_service()
        result = MagicMock()
        result.data = None
        ctx = _make_context(result=result)
        ext = _make_ext(svc, ctx)

        await ext._handle_mutation_invalidation()

        svc.invalidate.assert_not_called()

    async def test_extracts_tags_and_invalidates(self):
        svc = _make_cache_service()
        result = MagicMock()
        result.data = {
            "createUser": {"__typename": "User", "id": "42"},
        }
        ctx = _make_context(result=result)
        ext = _make_ext(svc, ctx)

        await ext._handle_mutation_invalidation()

        svc.invalidate.assert_awaited_once()
        tags = svc.invalidate.call_args[0][0]
        assert "User" in tags
        assert "User:42" in tags

    async def test_no_tags_skips_invalidation(self):
        svc = _make_cache_service()
        result = MagicMock()
        result.data = {"createUser": "ok"}
        ctx = _make_context(result=result)
        ext = _make_ext(svc, ctx)

        await ext._handle_mutation_invalidation()

        svc.invalidate.assert_not_called()


# ── _extract_tags_from_response ──────────────────────────────────────────


class TestExtractTagsFromResponse:
    def _make_ext(self):
        svc = _make_cache_service()
        ctx = _make_context()
        return _make_ext(svc, ctx)

    def test_dict_with_typename(self):
        ext = self._make_ext()
        tags = ext._extract_tags_from_response(
            {"createUser": {"__typename": "User"}}
        )
        assert "User" in tags

    def test_dict_with_typename_and_id(self):
        ext = self._make_ext()
        tags = ext._extract_tags_from_response(
            {"createUser": {"__typename": "User", "id": "1"}}
        )
        assert "User" in tags
        assert "User:1" in tags

    def test_nested_dicts_recursively_traversed(self):
        ext = self._make_ext()
        data = {
            "getOrder": {
                "__typename": "Order",
                "id": "10",
                "user": {"__typename": "User", "id": "5"},
            }
        }
        tags = ext._extract_tags_from_response(data)
        assert "Order" in tags
        assert "Order:10" in tags
        assert "User" in tags
        assert "User:5" in tags

    def test_lists_items_traversed(self):
        ext = self._make_ext()
        data = {
            "getUsers": [
                {"node": {"__typename": "User", "id": "1"}},
                {"node": {"__typename": "User", "id": "2"}},
            ]
        }
        tags = ext._extract_tags_from_response(data)
        assert "User" in tags
        assert "User:1" in tags
        assert "User:2" in tags

    def test_empty_dict_returns_empty(self):
        ext = self._make_ext()
        assert ext._extract_tags_from_response({}) == []

    def test_non_dict_returns_empty(self):
        ext = self._make_ext()
        assert ext._extract_tags_from_response("string") == []
        assert ext._extract_tags_from_response(42) == []
        assert ext._extract_tags_from_response(None) == []

    def test_no_typename_in_value(self):
        ext = self._make_ext()
        tags = ext._extract_tags_from_response(
            {"field": {"name": "test", "value": 42}}
        )
        assert tags == []

    def test_mixed_nesting_lists_and_dicts(self):
        ext = self._make_ext()
        data = {
            "search": {
                "__typename": "SearchResult",
                "items": [
                    {"post": {"__typename": "Post", "id": "1"}},
                    {"comment": {"__typename": "Comment", "id": "10"}},
                ],
            }
        }
        tags = ext._extract_tags_from_response(data)
        assert "SearchResult" in tags
        assert "Post" in tags
        assert "Post:1" in tags
        assert "Comment" in tags
        assert "Comment:10" in tags


# ── get_results ──────────────────────────────────────────────────────────


class TestGetResults:
    def test_not_cached_returns_false(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx)

        result = ext.get_results()

        assert result == {
            "cacheql": {
                "cached": False,
                "stats": {"hits": 0, "misses": 0, "total": 0},
            }
        }

    def test_cached_returns_true(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx)
        ext._cached_response = {"some": "data"}

        result = ext.get_results()

        assert result == {
            "cacheql": {
                "cached": True,
                "stats": {"hits": 0, "misses": 0, "total": 0},
            }
        }


# ── on_operation (integration of _check_cache + _cache_response) ─────────


class TestOnOperation:
    async def test_calls_check_cache_and_cache_response(self):
        svc = _make_cache_service()
        ctx = _make_context()
        ext = _make_ext(svc, ctx)

        with (
            patch.object(ext, "_check_cache", new_callable=AsyncMock) as mock_check,
            patch.object(ext, "_cache_response", new_callable=AsyncMock) as mock_cache,
        ):
            await _drive_async_gen(ext.on_operation())

            mock_check.assert_awaited_once()
            mock_cache.assert_awaited_once()

    async def test_check_cache_passes_session_context(self):
        config = CacheConfig(session_context_keys=["current_user_id"])
        svc = _make_cache_service(config=config)
        ctx = _make_context(context={"current_user_id": "42"})
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_awaited_once_with(
            operation_name="GetUser",
            query=ctx.query,
            variables={"id": "1"},
            context={"current_user_id": "42"},
        )

    async def test_cache_response_passes_session_context(self):
        config = CacheConfig(session_context_keys=["current_user_id"])
        svc = _make_cache_service(config=config)
        result = MagicMock()
        result.errors = None
        result.data = {"user": {"id": "1"}}
        ctx = _make_context(
            query="query GetUser { user { id } }",
            variables={"id": "1"},
            operation_name="GetUser",
            result=result,
            context={"current_user_id": "42"},
        )
        ext = _make_ext(svc, ctx)

        await ext._cache_response()

        svc.cache_response.assert_awaited_once_with(
            operation_name="GetUser",
            query="query GetUser { user { id } }",
            variables={"id": "1"},
            response={"user": {"id": "1"}},
            context={"current_user_id": "42"},
        )

    async def test_no_session_context_keys_passes_none(self):
        svc = _make_cache_service()  # default config has no session_context_keys
        ctx = _make_context(context={"current_user_id": "42"})
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_awaited_once_with(
            operation_name="GetUser",
            query=ctx.query,
            variables={"id": "1"},
            context=None,
        )

    async def test_context_not_dict_passes_none(self):
        config = CacheConfig(session_context_keys=["current_user_id"])
        svc = _make_cache_service(config=config)
        ctx = _make_context()
        ctx.context = "not-a-dict"
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_awaited_once_with(
            operation_name="GetUser",
            query=ctx.query,
            variables={"id": "1"},
            context=None,
        )

    async def test_no_matching_keys_passes_none(self):
        config = CacheConfig(session_context_keys=["current_user_id"])
        svc = _make_cache_service(config=config)
        ctx = _make_context(context={"other_key": "value"})
        ext = _make_ext(svc, ctx)

        await ext._check_cache()

        svc.get_cached_response.assert_awaited_once_with(
            operation_name="GetUser",
            query=ctx.query,
            variables={"id": "1"},
            context=None,
        )

    async def test_full_flow_cache_hit_exits_early(self):
        cached_data = {"user": {"id": "1"}}
        svc = _make_cache_service(cached_response=cached_data)
        result = MagicMock()
        result.errors = None
        result.data = cached_data
        ctx = _make_context(result=result, context={})
        ext = _make_ext(svc, ctx)

        await _drive_async_gen(ext.on_operation())

        assert ext._cached_response == cached_data
        svc.cache_response.assert_not_called()
