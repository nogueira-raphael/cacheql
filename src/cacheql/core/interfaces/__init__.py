"""Core interfaces (Protocol classes) for cacheql."""

from cacheql.core.interfaces.cache_backend import ICacheBackend
from cacheql.core.interfaces.invalidator import IInvalidator
from cacheql.core.interfaces.key_builder import IKeyBuilder
from cacheql.core.interfaces.serializer import ISerializer

__all__ = [
    "ICacheBackend",
    "IKeyBuilder",
    "ISerializer",
    "IInvalidator",
]
