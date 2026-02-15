"""Ariadne framework adapter for cacheql."""

from cacheql.adapters.ariadne.decorators import cached_resolver, invalidates_cache
from cacheql.adapters.ariadne.graphql import CachingGraphQL
from cacheql.adapters.ariadne.handler import CachingGraphQLHTTPHandler

__all__ = [
    "CachingGraphQL",
    "CachingGraphQLHTTPHandler",
    # Decorators for resolver-level caching
    "cached_resolver",
    "invalidates_cache",
]
