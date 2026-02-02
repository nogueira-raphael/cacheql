"""Ariadne-specific decorators for field-level caching."""

import functools
import re
from collections.abc import Callable
from datetime import timedelta
from typing import Any, TypeVar

from cacheql.core.services.cache_service import CacheService
from cacheql.infrastructure.key_builders.default import DefaultKeyBuilder

F = TypeVar("F", bound=Callable[..., Any])

# Global cache service reference for decorators
_cache_service: CacheService | None = None
_key_builder: DefaultKeyBuilder | None = None


def configure_cache(cache_service: CacheService) -> None:
    """Configure the global cache service for decorators.

    Args:
        cache_service: The cache service to use.
    """
    global _cache_service, _key_builder
    _cache_service = cache_service
    _key_builder = DefaultKeyBuilder(prefix=cache_service.config.key_prefix)


def cached_resolver(
    ttl: timedelta | None = None,
    tags: list[str] | None = None,
    key: str | Callable[..., str] | None = None,
) -> Callable[[F], F]:
    """Decorator for caching resolver results.

    Usage:
        @query.field("user")
        @cached_resolver(ttl=timedelta(minutes=10), tags=["User"])
        async def resolve_user(_, info, id: str):
            return await get_user(id)

    Args:
        ttl: Time-to-live for cached results.
        tags: Tags for cache invalidation.
        key: Custom key or key builder function.

    Returns:
        Decorated resolver function.
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
                return _cache_service._serializer.deserialize(cached_data)

            # Execute resolver
            result = await func(*args, **kwargs)

            # Cache result
            effective_ttl = ttl or _cache_service.config.default_ttl
            serialized = _cache_service._serializer.serialize(result)
            await _cache_service._backend.set(cache_key, serialized, effective_ttl)

            # Store tag mappings
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


def invalidates_cache(
    tags: list[str] | None = None,
) -> Callable[[F], F]:
    """Decorator for invalidating cache on mutation.

    Usage:
        @mutation.field("updateUser")
        @invalidates_cache(tags=["User", "User:{id}"])
        async def resolve_update_user(_, info, id: str, input: dict):
            return await update_user(id, input)

    Args:
        tags: Tags to invalidate. Supports {arg_name} interpolation.

    Returns:
        Decorated resolver function.
    """

    def decorator(func: F) -> F:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Execute mutation first
            result = await func(*args, **kwargs)

            # Invalidate cache
            if _cache_service is not None and tags:
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
    """Build cache key for a resolver call.

    Args:
        func: The resolver function.
        args: Positional arguments.
        kwargs: Keyword arguments.
        custom_key: Custom key or key builder function.

    Returns:
        The cache key string.
    """
    if _key_builder is None:
        raise RuntimeError("Cache not configured. Call configure_cache() first.")

    if custom_key is not None:
        if callable(custom_key):
            return custom_key(*args, **kwargs)
        return _interpolate_string(custom_key, args, kwargs)

    # Build default key from function name and arguments
    func_name = func.__name__
    type_name = _get_type_name_from_func(func)

    return _key_builder.build_field_key(
        type_name=type_name,
        field_name=func_name,
        args=kwargs if kwargs else None,
        parent_value=args[0] if args else None,
    )


def _get_type_name_from_func(func: Callable[..., Any]) -> str:
    """Extract GraphQL type name from function.

    Args:
        func: The resolver function.

    Returns:
        The type name or "Query" as default.
    """
    # Try to get from function metadata
    if hasattr(func, "_graphql_type"):
        return str(func._graphql_type)

    # Infer from function name
    name = func.__name__
    if name.startswith("resolve_"):
        return "Query"

    return "Query"


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
        args: Positional arguments (ignored for interpolation).
        kwargs: Keyword arguments for interpolation.

    Returns:
        Interpolated string.
    """
    # Find all {name} patterns
    pattern = r"\{(\w+)\}"

    def replacer(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in kwargs:
            return str(kwargs[name])
        return match.group(0)  # Keep original if not found

    return re.sub(pattern, replacer, template)
