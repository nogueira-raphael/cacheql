# CacheQL Example: FastAPI + Ariadne + Redis

This example demonstrates how to use **CacheQL** with FastAPI, Ariadne GraphQL, and Redis as the cache backend.

It follows the [Apollo Server caching semantics](https://www.apollographql.com/docs/apollo-server/performance/caching/) for the `@cacheControl` directive.

## Table of Contents

- [Quick Start](#quick-start)
- [Cache Control Directive](#cache-control-directive)
- [Setting Cache Hints](#setting-cache-hints)
  - [Static Hints (Schema)](#static-hints-schema)
  - [Dynamic Hints (Resolvers)](#dynamic-hints-resolvers)
- [Calculating Cache Behavior](#calculating-cache-behavior)
- [Default maxAge Behavior](#default-maxage-behavior)
- [Example Queries](#example-queries)
- [Cache Invalidation](#cache-invalidation)
- [Verifying Cache Behavior](#verifying-cache-behavior)

---

## Quick Start

### Requirements

- Docker and Docker Compose

### Running

```bash
docker-compose up --build
```

The application will be available at:
- **GraphQL Playground**: http://localhost:8000/graphql
- **Redis Commander** (UI): http://localhost:8081

### Stopping

```bash
docker-compose down
# To remove Redis data:
docker-compose down -v
```

---

## Cache Control Directive

CacheQL recognizes the `@cacheControl` directive, which you can use in your schema to define caching behavior for fields and types.

The directive definition is included via `get_cache_control_directive_sdl()` in [`app/schema.py`](app/schema.py):

```python
from cacheql.core.services.directive_parser import get_cache_control_directive_sdl

CACHE_CONTROL_SDL = get_cache_control_directive_sdl()
```

This adds the following to your schema:

```graphql
directive @cacheControl(
  maxAge: Int
  scope: CacheControlScope
  inheritMaxAge: Boolean
) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION

enum CacheControlScope {
  PUBLIC
  PRIVATE
}
```

| Argument | Description |
|----------|-------------|
| `maxAge` | Maximum time (in seconds) the field's cached value is valid. Default is `0`. |
| `scope` | `PUBLIC` (shared cache) or `PRIVATE` (per-user cache). Default is `PUBLIC`. |
| `inheritMaxAge` | If `true`, inherits `maxAge` from parent field instead of using default. |

---

## Setting Cache Hints

### Static Hints (Schema)

Use `@cacheControl` in the schema for fields that should always be cached with the same settings. See [`app/schema.py`](app/schema.py) for the complete schema.

#### Field-Level Definitions

From [`app/schema.py`](app/schema.py):

```graphql
type Query {
    """
    Get all users.
    Cached for 5 minutes (300 seconds), shared across all clients.
    """
    users: [User!]! @cacheControl(maxAge: 300)

    """
    Get the currently authenticated user.
    Cached for 1 minute, PRIVATE (per-user cache).
    """
    me: User @cacheControl(maxAge: 60, scope: PRIVATE)

    """
    Get database call statistics.
    Never cached (for debugging).
    """
    dbStats: DbStats @cacheControl(maxAge: 0)
}
```

**In this example:**
- `users` is cached for 300 seconds (5 minutes), shared by all clients
- `me` is cached for 60 seconds, but each user gets their own cached value
- `dbStats` is never cached (`maxAge: 0`)

#### Type-Level Definitions

From [`app/schema.py`](app/schema.py):

```graphql
"""
A user in the system.
Default cache of 10 minutes at the type level.
"""
type User @cacheControl(maxAge: 600) {
    id: ID!
    name: String!
    ...
}

"""
A blog post.
Default cache of 5 minutes.
"""
type Post @cacheControl(maxAge: 300) {
    id: ID!
    title: String!
    ...
}
```

Any field returning `User` will default to `maxAge: 600` (10 minutes), and any field returning `Post` will default to `maxAge: 300` (5 minutes).

#### Field Overriding Type

Field-level settings override type-level settings. From [`app/schema.py`](app/schema.py):

```graphql
type User @cacheControl(maxAge: 600) {
    id: ID!
    name: String!

    """
    Secret note - never cached (maxAge: 0).
    Including this field disables caching for the entire response.
    """
    secretNote: String @cacheControl(maxAge: 0)
}
```

Here, `secretNote` has `maxAge: 0`, which overrides the type's `maxAge: 600`. Including this field in a query will disable caching for the entire response.

#### Setting Scope Without maxAge

From [`app/schema.py`](app/schema.py):

```graphql
type User @cacheControl(maxAge: 600) {
    ...
    """
    User's email address.
    Marked as PRIVATE - will make entire response private if included.
    """
    email: String! @cacheControl(scope: PRIVATE)
}
```

Here, `email` inherits `maxAge: 600` from the `User` type but sets `scope: PRIVATE`. Including this field makes the entire response private.

#### Using inheritMaxAge

Use `inheritMaxAge` for fields that should inherit caching from their parent. From [`app/schema.py`](app/schema.py):

```graphql
type User @cacheControl(maxAge: 600) {
    ...
    """
    Posts written by this user.
    Inherits maxAge from parent field.
    """
    posts: [Post!]! @cacheControl(inheritMaxAge: true)
}

type Post @cacheControl(maxAge: 300) {
    ...
    """
    The post's author.
    Inherits maxAge from parent (Post's 300s or query field's value).
    """
    author: User! @cacheControl(inheritMaxAge: true)
}
```

**Why use inheritMaxAge?**
- When a field returns a non-scalar type, it defaults to `maxAge: 0`
- `inheritMaxAge: true` makes it inherit from the parent instead
- This is useful for nested relationships

---

### Dynamic Hints (Resolvers)

Cache hints can also be set dynamically based on runtime conditions. See [`app/resolvers.py`](app/resolvers.py).

#### Using set_cache_hint()

From [`app/resolvers.py`](app/resolvers.py):

```python
from cacheql.hints import set_cache_hint, private_cache, no_cache

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
```

#### Using no_cache()

From [`app/resolvers.py`](app/resolvers.py):

```python
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
        ...
    }
```

**Note:** Dynamic hints override static hints from the schema.

---

## Calculating Cache Behavior

For security, each response's cache behavior is calculated based on the **most restrictive** settings:

| Rule | Behavior |
|------|----------|
| `maxAge` | Uses the **lowest** value among all fields |
| `scope` | Uses `PRIVATE` if **any** field is `PRIVATE` |

### Example with email (PRIVATE scope)

```graphql
query {
  users {          # maxAge: 300, scope: PUBLIC
    name           # inherits from parent
    email          # scope: PRIVATE (inherits maxAge: 600 from User type)
  }
}
```

**Result:** `Cache-Control: max-age=300, private`

The response is `PRIVATE` because `email` has `scope: PRIVATE`.

### Example with secretNote (maxAge: 0)

```graphql
query {
  users {          # maxAge: 300
    name
    secretNote     # maxAge: 0
  }
}
```

**Result:** `Cache-Control: no-store`

The response is not cached because `secretNote` has `maxAge: 0`.

---

## Default maxAge Behavior

CacheQL follows Apollo Server's defaults:

| Field Type | Default maxAge |
|------------|----------------|
| Root fields (Query, Mutation) | `0` (no cache) |
| Fields returning non-scalar types | `0` (no cache) |
| Scalar fields | Inherit from parent |

**Why these defaults?**
- Root fields often fetch data, so they're not cached by default
- Non-scalar fields (objects, lists) may contain many nested fields
- Scalar fields rarely fetch data, so they inherit from parent

### Example Calculations with This Schema

| Query | Result maxAge | Explanation |
|-------|---------------|-------------|
| `{ users { id name } }` | `300` | `users` has `maxAge: 300` |
| `{ me { id name } }` | `60` | `me` has `maxAge: 60, scope: PRIVATE` |
| `{ user(id: "1") { id } }` | `600` | `user` has `maxAge: 600` |
| `{ users { secretNote } }` | `0` | `secretNote` has `maxAge: 0` |
| `{ posts { author { name } } }` | `300` | `author` inherits from `posts` (300) |

---

## Example Queries

### Public Cache (5 minutes)

```graphql
query {
  users {
    id
    name
  }
}
```

Response header: `Cache-Control: max-age=300, public`

### Private Cache (1 minute)

```graphql
query {
  me {
    id
    name
    email
  }
}
```

Response header: `Cache-Control: max-age=60, private`

### No Cache (sensitive data)

```graphql
query {
  users {
    id
    name
    secretNote
  }
}
```

Response header: `Cache-Control: no-store`

### Nested Query with inheritMaxAge

```graphql
query {
  user(id: "1") {
    id
    name
    posts {
      title
      author {
        name
      }
    }
  }
}
```

Response header: `Cache-Control: max-age=600, public`

(Both `posts` and `author` have `inheritMaxAge: true`, so they inherit from `user` which has `maxAge: 600`)

### Dynamic Cache Hint (public profile)

```graphql
query {
  user(id: "1") {
    id
    name
    isPublicProfile
  }
}
```

If `isPublicProfile` is `true`, the resolver sets `maxAge: 3600` (1 hour).
If `false`, it sets `maxAge: 60` with `scope: PRIVATE`.

---

## Cache Invalidation

Mutations invalidate related cache entries. From [`app/resolvers.py`](app/resolvers.py):

```python
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
```

### Try It

```graphql
mutation {
  updateUser(id: "1", name: "Alice Updated") {
    id
    name
  }
}
```

This invalidates cache entries tagged with `User` and `User:1`.

---

## Verifying Cache Behavior

### 1. Check Response Headers

In GraphQL Playground, look for:
- `Cache-Control: max-age=X, public|private`
- `X-Cache: HIT` (served from cache)

### 2. Check Redis

Via Redis Commander: http://localhost:8081

Or via CLI:

```bash
docker-compose exec redis redis-cli KEYS "*"
```

### 3. Check Cache Stats

```bash
curl http://localhost:8000/cache/stats
```

Returns:
```json
{
  "stats": { "hits": 5, "misses": 2 },
  "config": { "enabled": true, ... }
}
```

### 4. Clear Cache

```bash
curl -X POST http://localhost:8000/cache/clear
```

---

## Project Structure

```
app/
├── main.py          # FastAPI app with CacheQL configuration
├── schema.py        # GraphQL schema with @cacheControl directives
├── resolvers.py     # Resolvers with dynamic cache hints
└── database.py      # Fake in-memory database
```

---

## Configuration

From [`app/main.py`](app/main.py):

```python
from cacheql import CacheConfig, CacheService, DefaultKeyBuilder, JsonSerializer
from cacheql.adapters.ariadne import CachingGraphQL
from cacheql_redis import RedisCacheBackend

cache_config = CacheConfig(
    enabled=True,
    use_cache_control=True,      # Enable @cacheControl directive parsing
    default_max_age=0,           # Conservative: don't cache by default
    calculate_http_headers=True, # Generate Cache-Control headers
    key_prefix="example",
    cache_queries=True,
    cache_mutations=False,
)

cache_backend = RedisCacheBackend(
    redis_url=REDIS_URL,
    key_prefix="cacheql:example",
)

cache_service = CacheService(
    backend=cache_backend,
    key_builder=DefaultKeyBuilder(),
    serializer=JsonSerializer(),
    config=cache_config,
)

graphql_app = CachingGraphQL(
    schema,
    cache_service=cache_service,
    debug=DEBUG,
    context_value=get_context_value,
)
```

---

## References

- [Apollo Server - Caching](https://www.apollographql.com/docs/apollo-server/performance/caching/)
- [CacheQL Documentation](https://github.com/nogueira-raphael/cacheql)
