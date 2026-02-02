"""Ariadne framework adapter for cacheql."""

from cacheql.adapters.ariadne.decorators import cached_resolver, invalidates_cache
from cacheql.adapters.ariadne.extension import CacheExtension, create_cache_extension
from cacheql.adapters.ariadne.graphql import CachingGraphQL
from cacheql.adapters.ariadne.handler import CachingGraphQLHTTPHandler

__all__ = [
    # Recommended: Simple drop-in replacement for GraphQL
    "CachingGraphQL",
    "CachingGraphQLHTTPHandler",
    # Deprecated: Extension-based approach (doesn't work with async)
    "CacheExtension",
    "create_cache_extension",
    # Decorators for resolver-level caching
    "cached_resolver",
    "invalidates_cache",
]
