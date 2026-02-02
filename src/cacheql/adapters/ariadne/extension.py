"""Ariadne extension for GraphQL response caching.

Supports Apollo Server-style @cacheControl directives for fine-grained
cache control at the field and type level.

.. deprecated::
    CacheExtension is deprecated because Ariadne's extension system is
    synchronous and doesn't properly await async methods. Use CachingGraphQL
    instead for proper async support.
"""

import warnings
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from cacheql.core.entities.cache_control import (
    ResponseCachePolicy,
)
from cacheql.core.services.cache_control_calculator import (
    CacheControlCalculator,
    CacheControlContext,
)
from cacheql.core.services.cache_service import CacheService
from cacheql.core.services.directive_parser import DirectiveParser, SchemaDirectives
from cacheql.hints import CACHE_CONTROL_CONTEXT_KEY


class CacheExtension:
    """Ariadne extension for GraphQL response caching with cache control.

    Implements caching with support for @cacheControl directives,
    following Apollo Server's semantics.

    Usage:
        from cacheql import CacheService, CacheConfig
        from cacheql.adapters.ariadne import CacheExtension

        cache_service = CacheService(
            backend=InMemoryCacheBackend(),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
            config=CacheConfig(use_cache_control=True),
        )

        # Parse schema directives
        extension = CacheExtension(cache_service, schema=schema)

        app = GraphQL(
            schema,
            extensions=[extension],
        )

    With @cacheControl directives in schema:
        type Query {
            users: [User!]! @cacheControl(maxAge: 300)
            me: User @cacheControl(maxAge: 60, scope: PRIVATE)
        }

        type User @cacheControl(maxAge: 600) {
            id: ID!
            name: String!
            email: String! @cacheControl(scope: PRIVATE)
        }
    """

    def __init__(
        self,
        cache_service: CacheService,
        schema: Any | None = None,
        should_cache: Callable[[dict[str, Any]], bool] | None = None,
        set_http_headers: bool = True,
    ) -> None:
        """Initialize the cache extension.

        Args:
            cache_service: The cache service to use.
            schema: Optional GraphQL schema to parse directives from.
            should_cache: Optional callback to determine if a request should
                be cached. Receives the context dict and returns True/False.
            set_http_headers: Whether to set Cache-Control HTTP headers.

        .. deprecated::
            Use CachingGraphQL instead of CacheExtension. The extension system
            is synchronous and doesn't properly await async cache operations.
        """
        warnings.warn(
            "CacheExtension is deprecated because Ariadne's extension system is "
            "synchronous and doesn't properly await async methods. "
            "Use CachingGraphQL instead: "
            "from cacheql.adapters.ariadne import CachingGraphQL",
            DeprecationWarning,
            stacklevel=2,
        )
        self._cache_service = cache_service
        self._should_cache = should_cache
        self._set_http_headers = set_http_headers

        # Parse schema directives if schema provided
        self._schema_directives: SchemaDirectives | None = None
        if schema is not None:
            parser = DirectiveParser(
                default_max_age=cache_service.config.default_max_age
            )
            self._schema_directives = parser.parse_schema(schema)

        # Calculator for cache policies
        self._calculator = CacheControlCalculator(
            schema_directives=self._schema_directives,
            default_max_age=cache_service.config.default_max_age,
        )

        # Request state
        self._cached_response: Any | None = None
        self._cache_policy: ResponseCachePolicy | None = None
        self._is_mutation = False
        self._query: str | None = None
        self._variables: dict[str, Any] | None = None
        self._operation_name: str | None = None
        self._cache_control_context: CacheControlContext | None = None

    def set_schema_directives(self, directives: SchemaDirectives) -> None:
        """Set pre-parsed schema directives.

        Args:
            directives: The parsed schema directives.
        """
        self._schema_directives = directives
        self._calculator = CacheControlCalculator(
            schema_directives=directives,
            default_max_age=self._cache_service.config.default_max_age,
        )

    async def request_started(self, context: dict[str, Any]) -> None:
        """Called when a GraphQL request starts.

        Sets up cache control context and checks for cached response.

        Args:
            context: The request context containing query, variables, etc.
        """
        self._cached_response = None
        self._cache_policy = None
        self._is_mutation = False

        # Extract request details from context
        self._query = context.get("query") or context.get("request_body", {}).get(
            "query"
        )
        self._variables = context.get("variables") or context.get(
            "request_body", {}
        ).get("variables")
        self._operation_name = context.get("operation_name") or context.get(
            "request_body", {}
        ).get("operationName")

        # Create and inject cache control context
        self._cache_control_context = CacheControlContext(
            schema_directives=self._schema_directives or SchemaDirectives(),
            default_max_age=self._cache_service.config.default_max_age,
        )
        context[CACHE_CONTROL_CONTEXT_KEY] = self._cache_control_context

        if not self._query:
            return

        # Check if this is a mutation
        query_lower = self._query.lower().strip()
        if query_lower.startswith("mutation"):
            self._is_mutation = True
            return  # Don't cache mutations

        # Check custom should_cache callback
        if self._should_cache and not self._should_cache(context):
            return

        # Try to get cached response
        cached = await self._cache_service.get_cached_response(
            operation_name=self._operation_name,
            query=self._query,
            variables=self._variables,
        )

        if cached is not None:
            self._cached_response = cached
            context["_cacheql_cached_response"] = cached

    async def request_finished(self, context: dict[str, Any]) -> None:
        """Called when a GraphQL request finishes.

        Calculates cache policy and caches response if appropriate.

        Args:
            context: The request context.
        """
        # Skip if we served from cache
        if self._cached_response is not None:
            return

        # Skip mutations
        if self._is_mutation:
            if self._cache_service.config.auto_invalidate_on_mutation:
                await self._handle_mutation_invalidation(context)
            return

        # Get the response from context
        response = context.get("response")
        if response is None:
            return

        # Don't cache error responses
        if isinstance(response, dict) and response.get("errors"):
            return

        # Calculate cache policy from response data and hints
        data = response.get("data") if isinstance(response, dict) else response
        self._cache_policy = self._calculator.calculate_policy(
            data=data,
            context=self._cache_control_context,
        )

        # Only cache if policy allows
        if self._cache_policy.is_cacheable and self._query:
            ttl = timedelta(seconds=self._cache_policy.max_age)
            await self._cache_service.cache_response(
                operation_name=self._operation_name,
                query=self._query,
                variables=self._variables,
                response=response,
                ttl=ttl,
            )

        # Set HTTP headers if configured
        if self._set_http_headers:
            self._set_cache_control_header(context)

    def _set_cache_control_header(self, context: dict[str, Any]) -> None:
        """Set the Cache-Control HTTP header on the response.

        Args:
            context: The request context.
        """
        if self._cache_policy is None:
            return

        header_value = self._cache_policy.to_http_header()

        # Try to set header on response object
        response_obj = context.get("response_obj") or context.get("request")
        if response_obj and hasattr(response_obj, "headers"):
            response_obj.headers["Cache-Control"] = header_value

        # Store in context for middleware to pick up
        context["_cacheql_cache_control_header"] = header_value

    async def _handle_mutation_invalidation(self, context: dict[str, Any]) -> None:
        """Handle automatic cache invalidation on mutation.

        Args:
            context: The request context.
        """
        response = context.get("response")
        if not isinstance(response, dict):
            return

        data = response.get("data")
        if not data:
            return

        tags_to_invalidate = self._extract_tags_from_response(data)
        if tags_to_invalidate:
            await self._cache_service.invalidate(tags_to_invalidate)

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

    def format(self, context: dict[str, Any]) -> dict[str, Any] | None:
        """Add cache metadata to response extensions.

        Args:
            context: The request context.

        Returns:
            Dictionary with cache metadata for response extensions.
        """
        result: dict[str, Any] = {
            "cached": self._cached_response is not None,
            "stats": self._cache_service.stats,
        }

        # Add cache control info
        if self._cache_policy is not None:
            result["cacheControl"] = {
                "maxAge": self._cache_policy.max_age,
                "scope": self._cache_policy.scope.value,
                "cacheable": self._cache_policy.is_cacheable,
            }

        return {"cacheql": result}

    def has_cached_response(self) -> bool:
        """Check if a cached response is available.

        Returns:
            True if a cached response was found.
        """
        return self._cached_response is not None

    def get_cached_response(self) -> Any | None:
        """Get the cached response if available.

        Returns:
            The cached response, or None.
        """
        return self._cached_response

    def get_cache_policy(self) -> ResponseCachePolicy | None:
        """Get the calculated cache policy.

        Returns:
            The ResponseCachePolicy, or None if not calculated.
        """
        return self._cache_policy

    def get_cache_control_header(self) -> str | None:
        """Get the Cache-Control header value.

        Returns:
            The header value, or None if not set.
        """
        if self._cache_policy is None:
            return None
        return self._cache_policy.to_http_header()


# Convenience function to create extension with schema parsing
def create_cache_extension(
    cache_service: CacheService,
    schema: Any,
    **kwargs: Any,
) -> CacheExtension:
    """Create a CacheExtension with automatic schema directive parsing.

    Args:
        cache_service: The cache service to use.
        schema: The GraphQL schema to parse.
        **kwargs: Additional arguments for CacheExtension.

    Returns:
        A configured CacheExtension.
    """
    return CacheExtension(cache_service=cache_service, schema=schema, **kwargs)
