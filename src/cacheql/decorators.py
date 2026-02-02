"""Framework-agnostic cache decorators.

These decorators provide field-level caching for GraphQL resolvers.
They work with any GraphQL framework by using a configured CacheService.
"""

import functools
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from cacheql.core.services.cache_service import CacheService
from cacheql.infrastructure.key_builders.default import DefaultKeyBuilder

F = TypeVar("F", bound=Callable[..., Any])

# Module-level cache service reference
_cache_service: CacheService | None = None
_key_builder: DefaultKeyBuilder | None = None


def configure(cache_service: CacheService) -> None:
    """Configure the cache service for decorators.

    Must be called before using @cached or @invalidates decorators.

    Args:
        cache_service: The cache service instance to use.

    Example:
        cache_service = CacheService(
            backend=InMemoryCacheBackend(),
            key_builder=DefaultKeyBuilder(),
            serializer=JsonSerializer(),
        )
        configure(cache_service)
    """
    global _cache_service, _key_builder
    _cache_service = cache_service
    _key_builder = DefaultKeyBuilder(prefix=cache_service.config.key_prefix)


def get_cache_service() -> CacheService | None:
    """Get the configured cache service.

    Returns:
        The configured cache service, or None if not configured.
    """
    return _cache_service


def cached(
    ttl: timedelta | None = None,
    tags: list[str] | None = None,
    key: str | Callable[..., str] | None = None,
) -> Callable[[F], F]:
    """Decorator for caching async resolver results.

    Caches the result of an async function based on its arguments.
    Results are stored with optional TTL and tags for invalidation.

    Args:
        ttl: Time-to-live for cached results. Uses config default if None.
        tags: Tags for cache invalidation. Supports {arg_name} interpolation.
        key: Custom cache key or function to generate key.
            If string, supports {arg_name} interpolation.
            If callable, receives (*args, **kwargs) and returns key string.

    Returns:
        Decorated function.

    Example:
        @cached(ttl=timedelta(minutes=10), tags=["User", "User:{id}"])
        async def get_user(id: str) -> User:
            return await db.get_user(id)

        @cached(key=lambda id: f"user:{id}")
        async def get_user(id: str) -> User:
            return await db.get_user(id)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            if _cache_service is None or _key_builder is None:
                # Cache not configured, execute directly
                return await func(*args, **kwargs)

            # Build cache key
            cache_key = _build_cache_key(func, args, kwargs, key)

            # Try to get from cache
            cached_data = await _cache_service._backend.get(cache_key)
            if cached_data is not None:
                _cache_service._hits += 1
                return _cache_service._serializer.deserialize(cached_data)

            _cache_service._misses += 1

            # Execute function
            result = await func(*args, **kwargs)

            # Cache result
            effective_ttl = ttl or _cache_service.config.default_ttl
            serialized = _cache_service._serializer.serialize(result)
            await _cache_service._backend.set(cache_key, serialized, effective_ttl)

            # Store tag mappings for invalidation
            resolved_tags = _resolve_tags(tags, args, kwargs)
            if resolved_tags:
                for tag in resolved_tags:
                    prefix = _cache_service.config.key_prefix
                    tag_key = f"{prefix}:tag:{tag}:{cache_key}"
                    await _cache_service._backend.set(
                        tag_key, cache_key.encode(), effective_ttl
                    )

            return result

        return wrapper  # type: ignore

    return decorator


def invalidates(
    tags: list[str],
) -> Callable[[F], F]:
    """Decorator for invalidating cache entries on mutation.

    Executes the decorated function and then invalidates all cache
    entries matching the specified tags.

    Args:
        tags: Tags to invalidate. Supports {arg_name} interpolation.

    Returns:
        Decorated function.

    Example:
        @invalidates(tags=["User", "User:{id}"])
        async def update_user(id: str, data: dict) -> User:
            return await db.update_user(id, data)
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute function first
            result = await func(*args, **kwargs)

            # Invalidate cache entries by tags
            if _cache_service is not None:
                resolved_tags = _resolve_tags(tags, args, kwargs)
                await _cache_service.invalidate(resolved_tags)

            return result

        return wrapper  # type: ignore

    return decorator


def _build_cache_key(
    func: Callable[..., Any],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    custom_key: str | Callable[..., str] | None,
) -> str:
    """Build cache key for a function call.

    Args:
        func: The function being cached.
        args: Positional arguments.
        kwargs: Keyword arguments.
        custom_key: Custom key or key builder function.

    Returns:
        The cache key string.
    """
    if _key_builder is None:
        raise RuntimeError("Cache not configured. Call configure() first.")

    if custom_key is not None:
        if callable(custom_key):
            return custom_key(*args, **kwargs)
        return _interpolate_string(custom_key, args, kwargs)

    # Build default key from function module, name, and arguments
    module = func.__module__ or ""
    func_name = func.__name__

    return _key_builder.build_field_key(
        type_name=module.split(".")[-1] if module else "default",
        field_name=func_name,
        args=kwargs if kwargs else None,
        parent_value=args[0] if args else None,
    )


def _resolve_tags(
    tags: list[str] | None,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> list[str]:
    """Resolve tags with argument interpolation.

    Args:
        tags: Tag patterns with optional {arg} placeholders.
        args: Positional arguments.
        kwargs: Keyword arguments.

    Returns:
        List of resolved tag strings.
    """
    if not tags:
        return []

    resolved: list[str] = []
    for tag in tags:
        resolved_tag = _interpolate_string(tag, args, kwargs)
        resolved.append(resolved_tag)

    return resolved


def _interpolate_string(
    template: str,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    """Interpolate {arg_name} placeholders in string.

    Args:
        template: String with {arg_name} placeholders.
        args: Positional arguments (ignored for name-based interpolation).
        kwargs: Keyword arguments for interpolation.

    Returns:
        Interpolated string.
    """
    pattern = r"\{(\w+)\}"

    def replacer(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in kwargs:
            return str(kwargs[name])
        return match.group(0)  # Keep original if not found

    return re.sub(pattern, replacer, template)
