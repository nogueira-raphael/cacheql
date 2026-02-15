"""GraphQL resolvers with cache hints demonstration."""

from ariadne import MutationType, ObjectType, QueryType

from app import database as db
from cacheql.hints import no_cache, private_cache, set_cache_hint

# =============================================================================
# Query Resolvers
# =============================================================================

query = QueryType()


@query.field("users")
async def resolve_users(_, info):
    """
    Get all users.

    Cache hint is set via @cacheControl directive in schema (300s, PUBLIC).
    """
    return await db.get_users()


@query.field("user")
async def resolve_user(_, info, id: str):
    """
    Get a user by ID.

    Demonstrates dynamic cache hints based on data.
    """
    user = await db.get_user(id)

    if user is None:
        return None

    # Dynamic cache hint based on user data
    if user.get("is_public_profile"):
        # Public profiles can be cached longer
        set_cache_hint(info, max_age=3600, scope="PUBLIC")
    else:
        # Private profiles should be cached privately and shorter
        private_cache(info, max_age=60)

    return user


@query.field("me")
async def resolve_me(_, info):
    """
    Get the current user.

    Cache hint is set via @cacheControl directive (60s, PRIVATE).
    Requires "Authorization: Bearer user-{id}" header.
    """
    current_user_id = info.context.get("current_user_id")
    if not current_user_id:
        return None
    return await db.get_user(current_user_id)


@query.field("posts")
async def resolve_posts(_, info):
    """
    Get all posts.

    Cache hint is set via @cacheControl directive (300s, PUBLIC).
    """
    return await db.get_posts()


@query.field("post")
async def resolve_post(_, info, id: str):
    """Get a post by ID."""
    return await db.get_post(id)


@query.field("dbStats")
async def resolve_db_stats(_, info):
    """
    Get database call statistics.

    Demonstrates no_cache() - this field should never be cached.
    """
    # Explicitly disable caching (also set in schema)
    no_cache(info)

    return {
        "getUsersCalls": db.call_count["get_users"],
        "getUserCalls": db.call_count["get_user"],
        "getPostsCalls": db.call_count["get_posts"],
        "getPostCalls": db.call_count["get_post"],
        "getUserPostsCalls": db.call_count["get_user_posts"],
    }


# =============================================================================
# Mutation Resolvers
# =============================================================================

mutation = MutationType()


@mutation.field("updateUser")
async def resolve_update_user(_, info, id: str, name: str = None, email: str = None):
    """
    Update a user.

    This mutation will invalidate user-related caches.
    """
    user = await db.update_user(id, name=name, email=email)

    if user is None:
        return None

    # Get cache service from context to invalidate cache
    cache_service = info.context.get("cache_service")
    if cache_service:
        # Invalidate caches related to this user
        await cache_service.invalidate(["User", f"User:{id}"])
        print(f"[CACHE] Invalidated caches for User:{id}")

    return user


@mutation.field("createPost")
async def resolve_create_post(_, info, title: str, content: str, authorId: str):
    """
    Create a new post.

    Invalidates post-related caches.
    """
    post = await db.create_post(title=title, content=content, author_id=authorId)

    # Invalidate caches
    cache_service = info.context.get("cache_service")
    if cache_service:
        await cache_service.invalidate(["Post", f"User:{authorId}:posts"])
        print(f"[CACHE] Invalidated Post caches")

    return post


@mutation.field("deletePost")
async def resolve_delete_post(_, info, id: str):
    """
    Delete a post.

    Invalidates post-related caches.
    """
    # Get post to find author before deletion
    post = await db.get_post(id)
    deleted = await db.delete_post(id)

    if deleted and post:
        cache_service = info.context.get("cache_service")
        if cache_service:
            await cache_service.invalidate(["Post", f"Post:{id}"])
            print(f"[CACHE] Invalidated Post:{id} cache")

    return deleted


@mutation.field("resetDbStats")
async def resolve_reset_db_stats(_, info):
    """Reset database call statistics."""
    db.reset_call_count()
    return True


# =============================================================================
# Object Type Resolvers
# =============================================================================

user_type = ObjectType("User")


@user_type.field("posts")
async def resolve_user_posts(user, info):
    """Get posts for a user."""
    return await db.get_user_posts(user["id"])


@user_type.field("isPublicProfile")
def resolve_is_public_profile(user, info):
    """Resolve isPublicProfile field."""
    return user.get("is_public_profile", False)


@user_type.field("secretNote")
def resolve_secret_note(user, info):
    """
    Resolve secretNote field.

    This field has maxAge: 0 in schema, so including it
    will make the entire response non-cacheable.
    """
    return user.get("secret_note")


@user_type.field("createdAt")
def resolve_user_created_at(user, info):
    """Resolve createdAt field."""
    return user.get("created_at")


post_type = ObjectType("Post")


@post_type.field("author")
async def resolve_post_author(post, info):
    """Get the author of a post."""
    return await db.get_user(post["author_id"])


@post_type.field("createdAt")
def resolve_post_created_at(post, info):
    """Resolve createdAt field."""
    return post.get("created_at")


# Export all resolvers
resolvers = [query, mutation, user_type, post_type]
