"""Core domain layer for cacheql."""

from cacheql.core.entities import CacheConfig, CacheEntry, CacheKey
from cacheql.core.interfaces import (
    ICacheBackend,
    IInvalidator,
    IKeyBuilder,
    ISerializer,
)
from cacheql.core.services import CacheService

__all__ = [
    # Entities
    "CacheConfig",
    "CacheEntry",
    "CacheKey",
    # Interfaces
    "ICacheBackend",
    "IKeyBuilder",
    "ISerializer",
    "IInvalidator",
    # Services
    "CacheService",
]
