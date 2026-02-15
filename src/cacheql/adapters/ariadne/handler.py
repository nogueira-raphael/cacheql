"""Caching HTTP handler for Ariadne GraphQL."""

from collections.abc import Callable
from datetime import timedelta
from typing import Any

from ariadne.asgi.handlers import GraphQLHTTPHandler

from cacheql.core.entities.cache_control import ResponseCachePolicy
from cacheql.core.services.cache_control_calculator import CacheControlCalculator
from cacheql.core.services.cache_service import CacheService
from cacheql.core.services.directive_parser import DirectiveParser, SchemaDirectives


class CachingGraphQLHTTPHandler(GraphQLHTTPHandler):
    """HTTP handler that adds response caching to Ariadne.

    Intercepts query execution to check cache first, then caches responses
    using TTL values from @cacheControl directives.
    """

    def __init__(
        self,
        cache_service: CacheService,
        schema: Any = None,
        should_cache: Callable[[dict[str, Any]], bool] | None = None,
        set_http_headers: bool = True,
        debug: bool = False,
    ) -> None:
        super().__init__()
        self._cache_service = cache_service
        self._should_cache = should_cache
        self._set_http_headers = set_http_headers
        self._debug = debug

        self._schema_directives: SchemaDirectives | None = None
        if schema is not None:
            parser = DirectiveParser(
                default_max_age=cache_service.config.default_max_age
            )
            self._schema_directives = parser.parse_schema(schema)

        self._calculator = CacheControlCalculator(
            schema_directives=self._schema_directives,
            default_max_age=cache_service.config.default_max_age,
        )

    def _extract_session_context(self, context_value: Any) -> dict[str, Any] | None:
        keys = self._cache_service.config.session_context_keys
        if not keys or not isinstance(context_value, dict):
            return None
        ctx = {k: context_value[k] for k in keys if k in context_value}
        return ctx or None

    def _log(self, message: str) -> None:
        if self._debug:
            print(f"[CACHE] {message}")

    async def execute_graphql_query(
        self,
        request: Any,
        data: Any,
        *,
        context_value: Any = None,
        query_document: Any = None,
    ) -> tuple[bool, dict[str, Any]]:
        if not isinstance(data, dict):
            return await super().execute_graphql_query(
                request, data,
                context_value=context_value,
                query_document=query_document,
            )

        query = data.get("query", "")
        variables = data.get("variables")
        operation_name = data.get("operationName")

        # Don't cache mutations
        if query and query.strip().lower().startswith("mutation"):
            self._log("Skipping cache for mutation")
            return await super().execute_graphql_query(
                request, data,
                context_value=context_value,
                query_document=query_document,
            )

        # Check should_cache callback
        if self._should_cache and not self._should_cache(data):
            self._log("Skipping cache per should_cache callback")
            return await super().execute_graphql_query(
                request, data,
                context_value=context_value,
                query_document=query_document,
            )

        # Resolve context before cache lookup so session keys are available
        if context_value is None:
            context_value = await self.get_context_for_request(request, data)

        # Try cache first
        session_context = self._extract_session_context(context_value)
        cached = await self._cache_service.get_cached_response(
            operation_name=operation_name,
            query=query,
            variables=variables,
            context=session_context,
        )

        if cached is not None:
            self._log("HIT")
            self._mark_cache_hit(request)
            return True, cached

        self._log("MISS")

        # Execute query
        success, response = await super().execute_graphql_query(
            request, data, context_value=context_value, query_document=query_document
        )

        # Cache successful responses
        if success and isinstance(response, dict) and not response.get("errors"):
            response_data = response.get("data")
            policy = self._calculator.calculate_policy(data=response_data)

            if policy.is_cacheable:
                ttl = timedelta(seconds=policy.max_age)
                await self._cache_service.cache_response(
                    operation_name=operation_name,
                    query=query,
                    variables=variables,
                    response=response,
                    ttl=ttl,
                    context=session_context,
                )
                self._log(f"Cached (TTL: {policy.max_age}s)")

            if self._set_http_headers:
                self._set_cache_headers(request, policy)

        return success, response

    def _mark_cache_hit(self, request: Any) -> None:
        if hasattr(request, "state"):
            request.state.cache_hit = True

    def _set_cache_headers(self, request: Any, policy: ResponseCachePolicy) -> None:
        header = policy.to_http_header()
        if hasattr(request, "state"):
            request.state.cache_control_header = header
        self._log(f"Cache-Control: {header}")
