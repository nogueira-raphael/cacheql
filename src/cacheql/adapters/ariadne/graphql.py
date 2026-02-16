"""Caching GraphQL ASGI app for Ariadne."""

from collections.abc import Callable
from typing import Any

from ariadne.asgi import GraphQL

from cacheql.adapters.ariadne.handler import CachingGraphQLHTTPHandler
from cacheql.core.services.cache_service import CacheService


class CachingGraphQL(GraphQL):
    """Drop-in replacement for Ariadne's GraphQL with built-in caching.

    Automatically caches responses based on @cacheControl directives.

    Example::

        app = CachingGraphQL(
            schema,
            cache_service=cache_service,
            debug=True,
        )
    """

    def __init__(
        self,
        schema: Any,
        cache_service: CacheService,
        should_cache: Callable[[dict[str, Any]], bool] | None = None,
        session_id: Callable[[Any], str | None] | None = None,
        set_http_headers: bool = True,
        **kwargs: Any,
    ) -> None:
        debug = kwargs.get("debug", False)

        http_handler = CachingGraphQLHTTPHandler(
            cache_service=cache_service,
            schema=schema,
            should_cache=should_cache,
            session_id=session_id,
            set_http_headers=set_http_headers,
            debug=debug,
        )

        super().__init__(schema, http_handler=http_handler, **kwargs)

        self._cache_service = cache_service
        self._caching_handler = http_handler

    @property
    def cache_service(self) -> CacheService:
        return self._cache_service

    @property
    def cache_stats(self) -> dict[str, int]:
        return self._cache_service.stats
