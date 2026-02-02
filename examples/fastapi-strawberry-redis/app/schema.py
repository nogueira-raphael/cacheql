"""Strawberry GraphQL schema with cache hints."""


import strawberry
from strawberry.types import Info

from app import database as db
from cacheql.hints import no_cache, private_cache, set_cache_hint


@strawberry.type
class User:
    """A user in the system."""

    id: strawberry.ID
    name: str
    email: str
    secret_note: str | None = None
    is_public_profile: bool = True
    created_at: str = ""

    @strawberry.field
    async def posts(self) -> list["Post"]:
        """Get posts by this user."""
        posts_data = await db.get_user_posts(self.id)
        return [Post.from_dict(p) for p in posts_data]

    @classmethod
    def from_dict(cls, data: dict) -> "User":
        """Create User from dictionary."""
        return cls(
            id=strawberry.ID(data["id"]),
            name=data["name"],
            email=data["email"],
            secret_note=data.get("secret_note"),
            is_public_profile=data.get("is_public_profile", True),
            created_at=data.get("created_at", ""),
        )


@strawberry.type
class Post:
    """A blog post."""

    id: strawberry.ID
    title: str
    content: str
    author_id: str
    created_at: str = ""

    @strawberry.field
    async def author(self) -> User | None:
        """Get the post author."""
        user_data = await db.get_user(self.author_id)
        return User.from_dict(user_data) if user_data else None

    @classmethod
    def from_dict(cls, data: dict) -> "Post":
        """Create Post from dictionary."""
        return cls(
            id=strawberry.ID(data["id"]),
            title=data["title"],
            content=data["content"],
            author_id=data["author_id"],
            created_at=data.get("created_at", ""),
        )


@strawberry.type
class DbStats:
    """Database call statistics for debugging."""

    get_users_calls: int
    get_user_calls: int
    get_posts_calls: int
    get_post_calls: int
    get_user_posts_calls: int


@strawberry.type
class Query:
    """GraphQL Query type."""

    @strawberry.field
    async def users(self, info: Info) -> list[User]:
        """Get all users. Cached for 5 minutes."""
        set_cache_hint(info, max_age=300, scope="PUBLIC")
        users_data = await db.get_users()
        return [User.from_dict(u) for u in users_data]

    @strawberry.field
    async def user(self, info: Info, id: strawberry.ID) -> User | None:
        """Get a user by ID. Cache depends on profile visibility."""
        user_data = await db.get_user(str(id))
        if user_data is None:
            return None

        # Dynamic cache hint based on profile visibility
        if user_data.get("is_public_profile"):
            set_cache_hint(info, max_age=3600, scope="PUBLIC")
        else:
            private_cache(info, max_age=60)

        return User.from_dict(user_data)

    @strawberry.field
    async def me(self, info: Info) -> User | None:
        """Get the current user. Private cache for 1 minute."""
        private_cache(info, max_age=60)
        user_data = await db.get_current_user()
        return User.from_dict(user_data) if user_data else None

    @strawberry.field
    async def posts(self, info: Info) -> list[Post]:
        """Get all posts. Cached for 5 minutes."""
        set_cache_hint(info, max_age=300, scope="PUBLIC")
        posts_data = await db.get_posts()
        return [Post.from_dict(p) for p in posts_data]

    @strawberry.field
    async def post(self, info: Info, id: strawberry.ID) -> Post | None:
        """Get a post by ID. Cached for 5 minutes."""
        set_cache_hint(info, max_age=300, scope="PUBLIC")
        post_data = await db.get_post(str(id))
        return Post.from_dict(post_data) if post_data else None

    @strawberry.field
    async def db_stats(self, info: Info) -> DbStats:
        """Get database call statistics. Never cached."""
        no_cache(info)
        return DbStats(
            get_users_calls=db.call_count["get_users"],
            get_user_calls=db.call_count["get_user"],
            get_posts_calls=db.call_count["get_posts"],
            get_post_calls=db.call_count["get_post"],
            get_user_posts_calls=db.call_count["get_user_posts"],
        )


@strawberry.type
class Mutation:
    """GraphQL Mutation type."""

    @strawberry.mutation
    async def update_user(
        self,
        info: Info,
        id: strawberry.ID,
        name: str | None = None,
        email: str | None = None,
    ) -> User | None:
        """Update a user. Invalidates user caches."""
        user_data = await db.update_user(str(id), name=name, email=email)
        if user_data is None:
            return None

        # Invalidate cache
        cache_service = info.context.get("cache_service")
        if cache_service:
            await cache_service.invalidate(["User", f"User:{id}"])
            print(f"[CACHE] Invalidated caches for User:{id}")

        return User.from_dict(user_data)

    @strawberry.mutation
    async def create_post(
        self,
        info: Info,
        title: str,
        content: str,
        author_id: strawberry.ID,
    ) -> Post:
        """Create a new post. Invalidates post caches."""
        post_data = await db.create_post(
            title=title, content=content, author_id=str(author_id)
        )

        # Invalidate cache
        cache_service = info.context.get("cache_service")
        if cache_service:
            await cache_service.invalidate(["Post", f"User:{author_id}:posts"])
            print("[CACHE] Invalidated Post caches")

        return Post.from_dict(post_data)

    @strawberry.mutation
    async def delete_post(self, info: Info, id: strawberry.ID) -> bool:
        """Delete a post. Invalidates post caches."""
        post_data = await db.get_post(str(id))
        deleted = await db.delete_post(str(id))

        if deleted and post_data:
            cache_service = info.context.get("cache_service")
            if cache_service:
                await cache_service.invalidate(["Post", f"Post:{id}"])
                print(f"[CACHE] Invalidated Post:{id} cache")

        return deleted

    @strawberry.mutation
    async def reset_db_stats(self) -> bool:
        """Reset database call statistics."""
        db.reset_call_count()
        return True


schema = strawberry.Schema(query=Query, mutation=Mutation)
