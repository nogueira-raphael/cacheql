"""Strawberry extension for GraphQL response caching."""

from collections.abc import AsyncIterator, Callable
from typing import TYPE_CHECKING, Any

from strawberry.extensions import SchemaExtension

from cacheql.core.services.cache_service import CacheService

if TYPE_CHECKING:
    from strawberry.types import ExecutionContext


def CacheExtension(  # noqa: N802 - PascalCase intentional for class factory
    cache_service: CacheService,
    should_cache: Callable[["ExecutionContext"], bool] | None = None,
) -> type[SchemaExtension]:
    """Create a Strawberry cache extension configured with the given service.

    Args:
        cache_service: The cache service to use.
        should_cache: Optional callback to determine if a request should
            be cached. Receives the execution context and returns True/False.

    Returns:
        A configured SchemaExtension class.

    Usage:
        from strawberry import Schema
        from cacheql import CacheService
        from cacheql.adapters.strawberry import CacheExtension

        cache_service = CacheService(
            backend=InMemoryCacheBackend(),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
        )

        schema = Schema(
            query=Query,
            extensions=[CacheExtension(cache_service)],
        )
    """

    class _CacheExtension(SchemaExtension):
        """Strawberry SchemaExtension for GraphQL response caching."""

        def __init__(
            self,
            *,
            execution_context: "ExecutionContext | None" = None,
        ) -> None:
            """Initialize the cache extension instance."""
            super().__init__(execution_context=execution_context)
            self._cached_response: Any | None = None
            self._is_mutation = False

        async def on_operation(self) -> AsyncIterator[None]:
            """Hook called around operation execution."""
            await self._check_cache()
            yield
            await self._cache_response()

        async def on_execute(self) -> AsyncIterator[None]:
            """Hook called around query execution.

            If we have a cached response, set result before execution.
            """
            if self._cached_response is not None:
                # We have a cached response - set result before yield
                from strawberry.types.execution import ExecutionResult

                ctx = self.execution_context
                ctx.result = ExecutionResult(data=self._cached_response, errors=[])
            yield
            # After execution - if we had cached, restore the cached result
            # (in case execution overwrote it)
            if self._cached_response is not None:
                from strawberry.types.execution import ExecutionResult

                ctx = self.execution_context
                ctx.result = ExecutionResult(data=self._cached_response, errors=[])

        async def _check_cache(self) -> None:
            """Check cache before execution."""
            ctx = self.execution_context

            query = ctx.query if hasattr(ctx, "query") else None
            if not query:
                return

            variables = ctx.variables if hasattr(ctx, "variables") else None
            operation_name = (
                ctx.operation_name if hasattr(ctx, "operation_name") else None
            )

            try:
                if hasattr(ctx, "operation_type") and ctx.operation_type is not None:
                    op_type = str(ctx.operation_type).upper()
                    self._is_mutation = "MUTATION" in op_type
                else:
                    query_lower = query.lower().strip()
                    self._is_mutation = query_lower.startswith("mutation")
            except RuntimeError:
                # operation_type may raise if document not yet parsed
                query_lower = query.lower().strip()
                self._is_mutation = query_lower.startswith("mutation")

            if self._is_mutation and not cache_service.config.cache_mutations:
                return

            if should_cache and not should_cache(ctx):
                return

            cached = await cache_service.get_cached_response(
                operation_name=operation_name,
                query=query,
                variables=variables,
            )

            if cached is not None:
                self._cached_response = cached
                if hasattr(ctx, "context") and ctx.context is not None:
                    ctx.context["_cacheql_cached_response"] = cached

        async def _cache_response(self) -> None:
            """Cache response after execution."""
            if self._cached_response is not None:
                return

            ctx = self.execution_context

            if self._is_mutation and not cache_service.config.cache_mutations:
                if cache_service.config.auto_invalidate_on_mutation:
                    await self._handle_mutation_invalidation()
                return

            result = ctx.result if hasattr(ctx, "result") else None
            if result is None:
                return

            if hasattr(result, "errors") and result.errors:
                return

            query = ctx.query if hasattr(ctx, "query") else None
            if not query:
                return

            variables = ctx.variables if hasattr(ctx, "variables") else None
            operation_name = (
                ctx.operation_name if hasattr(ctx, "operation_name") else None
            )

            data = result.data if hasattr(result, "data") else result
            await cache_service.cache_response(
                operation_name=operation_name,
                query=query,
                variables=variables,
                response=data,
            )

        async def _handle_mutation_invalidation(self) -> None:
            """Handle automatic cache invalidation on mutation."""
            ctx = self.execution_context
            result = ctx.result if hasattr(ctx, "result") else None

            if result is None:
                return

            data = result.data if hasattr(result, "data") else result
            if not data:
                return

            tags = self._extract_tags_from_response(data)
            if tags:
                await cache_service.invalidate(tags)

        def _extract_tags_from_response(self, data: Any) -> list[str]:
            """Extract cache tags from mutation response data."""
            tags: list[str] = []

            if isinstance(data, dict):
                for _key, value in data.items():
                    if isinstance(value, dict):
                        type_name = value.get("__typename")
                        if type_name:
                            tags.append(type_name)
                            if "id" in value:
                                tags.append(f"{type_name}:{value['id']}")
                        tags.extend(self._extract_tags_from_response(value))
                    elif isinstance(value, list):
                        for item in value:
                            tags.extend(self._extract_tags_from_response(item))

            return tags

        def get_results(self) -> dict[str, Any]:
            """Return cache metadata for response extensions."""
            return {
                "cacheql": {
                    "cached": self._cached_response is not None,
                    "stats": cache_service.stats,
                }
            }

    return _CacheExtension
