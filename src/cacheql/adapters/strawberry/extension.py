"""Strawberry extension for GraphQL response caching."""

from collections.abc import Callable, Iterator
from typing import TYPE_CHECKING, Any

from cacheql.core.services.cache_service import CacheService

if TYPE_CHECKING:
    from strawberry.types import ExecutionContext


class CacheExtension:
    """Strawberry SchemaExtension for GraphQL response caching.

    Implements query-level caching by intercepting requests before
    execution and caching responses after successful execution.

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

    def __init__(
        self,
        cache_service: CacheService,
        should_cache: Callable[["ExecutionContext"], bool] | None = None,
    ) -> None:
        """Initialize the cache extension.

        Args:
            cache_service: The cache service to use.
            should_cache: Optional callback to determine if a request should
                be cached. Receives the execution context and returns True/False.
        """
        self._cache_service = cache_service
        self._should_cache = should_cache

    def __call__(
        self,
        *,
        execution_context: "ExecutionContext",
    ) -> "CacheExtensionInstance":
        """Create an extension instance for a request.

        Args:
            execution_context: The Strawberry execution context.

        Returns:
            A new extension instance for this request.
        """
        return CacheExtensionInstance(
            cache_service=self._cache_service,
            should_cache=self._should_cache,
            execution_context=execution_context,
        )


class CacheExtensionInstance:
    """Instance of CacheExtension for a single request."""

    def __init__(
        self,
        cache_service: CacheService,
        should_cache: Callable[["ExecutionContext"], bool] | None,
        execution_context: "ExecutionContext",
    ) -> None:
        """Initialize the extension instance.

        Args:
            cache_service: The cache service to use.
            should_cache: Optional callback for cache decisions.
            execution_context: The Strawberry execution context.
        """
        self._cache_service = cache_service
        self._should_cache = should_cache
        self._execution_context = execution_context
        self._cached_response: Any | None = None
        self._is_mutation = False

    def on_operation(self) -> Iterator[None]:
        """Hook called around operation execution.

        Yields once before execution and once after.
        """
        # Before execution - check cache
        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_until_complete(self._check_cache())

        yield  # Execution happens here

        # After execution - cache response
        loop.run_until_complete(self._cache_response())

    async def _check_cache(self) -> None:
        """Check cache before execution."""
        ctx = self._execution_context

        # Get query details
        query = ctx.query if hasattr(ctx, "query") else None
        if not query:
            return

        variables = ctx.variables if hasattr(ctx, "variables") else None
        operation_name = ctx.operation_name if hasattr(ctx, "operation_name") else None

        # Check if this is a mutation
        if hasattr(ctx, "operation_type"):
            from strawberry.types import OperationType

            self._is_mutation = ctx.operation_type == OperationType.MUTATION
        else:
            # Fallback: check query string
            query_lower = query.lower().strip()
            self._is_mutation = query_lower.startswith("mutation")

        # Don't cache mutations unless configured
        if self._is_mutation and not self._cache_service.config.cache_mutations:
            return

        # Check custom should_cache callback
        if self._should_cache and not self._should_cache(ctx):
            return

        # Try to get cached response
        cached = await self._cache_service.get_cached_response(
            operation_name=operation_name,
            query=query,
            variables=variables,
        )

        if cached is not None:
            self._cached_response = cached
            # Store in context for potential short-circuit
            if hasattr(ctx, "context"):
                ctx.context["_cacheql_cached_response"] = cached

    async def _cache_response(self) -> None:
        """Cache response after execution."""
        # Skip if we served from cache
        if self._cached_response is not None:
            return

        ctx = self._execution_context

        # Skip mutations if not configured
        if self._is_mutation and not self._cache_service.config.cache_mutations:
            # Auto-invalidate on mutation if configured
            if self._cache_service.config.auto_invalidate_on_mutation:
                await self._handle_mutation_invalidation()
            return

        # Get response from execution context
        result = ctx.result if hasattr(ctx, "result") else None
        if result is None:
            return

        # Don't cache error responses
        if hasattr(result, "errors") and result.errors:
            return

        # Get query details
        query = ctx.query if hasattr(ctx, "query") else None
        if not query:
            return

        variables = ctx.variables if hasattr(ctx, "variables") else None
        operation_name = ctx.operation_name if hasattr(ctx, "operation_name") else None

        # Cache the response data
        data = result.data if hasattr(result, "data") else result
        await self._cache_service.cache_response(
            operation_name=operation_name,
            query=query,
            variables=variables,
            response=data,
        )

    async def _handle_mutation_invalidation(self) -> None:
        """Handle automatic cache invalidation on mutation."""
        ctx = self._execution_context
        result = ctx.result if hasattr(ctx, "result") else None

        if result is None:
            return

        data = result.data if hasattr(result, "data") else result
        if not data:
            return

        # Extract types to invalidate from response
        tags = self._extract_tags_from_response(data)
        if tags:
            await self._cache_service.invalidate(tags)

    def _extract_tags_from_response(self, data: Any) -> list[str]:
        """Extract cache tags from mutation response data.

        Args:
            data: The response data.

        Returns:
            List of tags to invalidate.
        """
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
        """Return cache metadata for response extensions.

        Returns:
            Dictionary with cache metadata.
        """
        return {
            "cacheql": {
                "cached": self._cached_response is not None,
                "stats": self._cache_service.stats,
            }
        }
