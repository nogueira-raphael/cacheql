"""Dynamic cache hints for GraphQL resolvers.

This module provides functions for setting cache hints dynamically
from within resolver code, similar to Apollo Server's cacheControlFromInfo.

Usage with Ariadne:
    from cacheql.hints import set_cache_hint

    @query.field("user")
    async def resolve_user(_, info, id: str):
        # Set cache hint dynamically based on data
        user = await get_user(id)
        if user.is_public:
            set_cache_hint(info, max_age=3600, scope="PUBLIC")
        else:
            set_cache_hint(info, max_age=60, scope="PRIVATE")
        return user

Usage with Strawberry:
    from cacheql.hints import set_cache_hint

    @strawberry.field
    async def user(self, info: Info, id: str) -> User:
        set_cache_hint(info, max_age=300)
        return await get_user(id)
"""

from typing import Any

from cacheql.core.entities.cache_control import CacheHint, CacheScope
from cacheql.core.services.cache_control_calculator import CacheControlContext

# Context key for cache control
CACHE_CONTROL_CONTEXT_KEY = "_cacheql_cache_control"


def get_cache_control(info: Any) -> CacheControlContext | None:
    """Get the cache control context from GraphQL info.

    Args:
        info: The GraphQL resolver info object.

    Returns:
        The CacheControlContext, or None if not available.
    """
    context = _get_context_dict(info)
    if context is None:
        return None
    return context.get(CACHE_CONTROL_CONTEXT_KEY)


def set_cache_hint(
    info: Any,
    max_age: int | None = None,
    scope: CacheScope | str | None = None,
) -> bool:
    """Set a cache hint for the current field.

    This is the equivalent of Apollo's cacheControl.setCacheHint().
    The hint will be used when calculating the overall cache policy.

    Args:
        info: The GraphQL resolver info object.
        max_age: Maximum cache age in seconds.
        scope: Cache scope ("PUBLIC" or "PRIVATE").

    Returns:
        True if the hint was set, False if cache control is not available.

    Example:
        @query.field("user")
        async def resolve_user(_, info, id: str):
            set_cache_hint(info, max_age=300, scope="PRIVATE")
            return await get_user(id)
    """
    cache_control = get_cache_control(info)
    if cache_control is None:
        return False

    cache_control.set_cache_hint(max_age=max_age, scope=scope)
    return True


def cache_hint(
    max_age: int | None = None,
    scope: CacheScope | str | None = None,
) -> CacheHint:
    """Create a CacheHint object.

    Convenience function for creating cache hints.

    Args:
        max_age: Maximum cache age in seconds.
        scope: Cache scope ("PUBLIC" or "PRIVATE").

    Returns:
        A new CacheHint instance.
    """
    parsed_scope: CacheScope | None = None
    if scope is not None:
        parsed_scope = CacheScope(scope.upper()) if isinstance(scope, str) else scope

    return CacheHint(max_age=max_age, scope=parsed_scope)


def no_cache(info: Any) -> bool:
    """Disable caching for the current field.

    Sets maxAge to 0, which will make the entire response non-cacheable.

    Args:
        info: The GraphQL resolver info object.

    Returns:
        True if set, False if cache control is not available.

    Example:
        @query.field("sensitive_data")
        async def resolve_sensitive(_, info):
            no_cache(info)
            return get_sensitive_data()
    """
    return set_cache_hint(info, max_age=0)


def private_cache(info: Any, max_age: int) -> bool:
    """Set a private cache hint for user-specific data.

    Args:
        info: The GraphQL resolver info object.
        max_age: Maximum cache age in seconds.

    Returns:
        True if set, False if cache control is not available.

    Example:
        @query.field("my_profile")
        async def resolve_my_profile(_, info):
            private_cache(info, max_age=300)
            return get_current_user_profile(info)
    """
    return set_cache_hint(info, max_age=max_age, scope=CacheScope.PRIVATE)


def public_cache(info: Any, max_age: int) -> bool:
    """Set a public cache hint for shared data.

    Args:
        info: The GraphQL resolver info object.
        max_age: Maximum cache age in seconds.

    Returns:
        True if set, False if cache control is not available.

    Example:
        @query.field("featured_posts")
        async def resolve_featured(_, info):
            public_cache(info, max_age=3600)
            return get_featured_posts()
    """
    return set_cache_hint(info, max_age=max_age, scope=CacheScope.PUBLIC)


def _get_context_dict(info: Any) -> dict[str, Any] | None:
    """Extract the context dictionary from resolver info.

    Handles different GraphQL framework info structures.

    Args:
        info: The GraphQL resolver info object.

    Returns:
        The context dictionary, or None if not found.
    """
    # Ariadne/graphql-core style
    if hasattr(info, "context"):
        context = info.context
        if isinstance(context, dict):
            return context
        # Strawberry style (context is an object with attributes)
        if hasattr(context, "__dict__"):
            ctx_dict: dict[str, Any] = context.__dict__
            return ctx_dict

    return None


def inject_cache_control_context(
    context: dict[str, Any],
    cache_control: CacheControlContext,
) -> None:
    """Inject cache control context into GraphQL context.

    This should be called when setting up the request context.

    Args:
        context: The GraphQL context dictionary.
        cache_control: The cache control context to inject.
    """
    context[CACHE_CONTROL_CONTEXT_KEY] = cache_control
