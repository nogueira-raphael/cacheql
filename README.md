# cacheql

Server-side caching framework for GraphQL APIs in Python.

**Compatible with Apollo Server's `@cacheControl` directive semantics.**

## Features

- **Apollo-style Cache Control**: Full support for `@cacheControl` directives
- **Query-level caching**: Cache entire GraphQL query responses
- **Field-level caching**: Fine-grained cache control per field and type
- **Dynamic cache hints**: Set cache policies from within resolvers
- **HTTP Cache-Control headers**: Automatic header generation
- **Multiple backends**: In-memory (LRU) and Redis support
- **Framework adapters**: Built-in support for Ariadne and Strawberry
- **Tag-based invalidation**: Invalidate cache entries by tags
- **Async-first**: Fully async API for modern Python applications

## Installation

```bash
# Core package with in-memory backend
pip install cacheql

# With Ariadne support
pip install cacheql[ariadne]

# With Strawberry support
pip install cacheql[strawberry]

# With Redis backend
pip install cacheql[redis]

# All optional dependencies
pip install cacheql[all]
```

## Quick Start with @cacheControl Directives

Following [Apollo Server's caching documentation](https://www.apollographql.com/docs/apollo-server/performance/caching), cacheql supports the `@cacheControl` directive for declarative cache configuration.

### Schema Setup

```graphql
# Add the directive definition to your schema
directive @cacheControl(
  maxAge: Int
  scope: CacheControlScope
  inheritMaxAge: Boolean
) on FIELD_DEFINITION | OBJECT | INTERFACE | UNION

enum CacheControlScope {
  PUBLIC
  PRIVATE
}

# Apply directives to types and fields
type Query {
  # Cache for 5 minutes, shared across all users
  users: [User!]! @cacheControl(maxAge: 300)

  # Cache for 1 minute, per-user only
  me: User @cacheControl(maxAge: 60, scope: PRIVATE)
}

type User @cacheControl(maxAge: 600) {
  id: ID!
  name: String!
  # Private data - makes entire response private
  email: String! @cacheControl(scope: PRIVATE)
}

type Post @cacheControl(maxAge: 300) {
  id: ID!
  title: String!
  # Inherit maxAge from parent (Post's 300s)
  author: User! @cacheControl(inheritMaxAge: true)
}
```

### Python Setup with Ariadne

```python
from ariadne import QueryType, make_executable_schema
from fastapi import FastAPI

from cacheql import (
    CacheService,
    CacheConfig,
    InMemoryCacheBackend,
    DefaultKeyBuilder,
    JsonSerializer,
    get_cache_control_directive_sdl,
)
from cacheql.adapters.ariadne import CachingGraphQL

# Include directive definition in your schema
type_defs = get_cache_control_directive_sdl() + """
    type Query {
        users: [User!]! @cacheControl(maxAge: 300)
        me: User @cacheControl(maxAge: 60, scope: PRIVATE)
    }

    type User @cacheControl(maxAge: 600) {
        id: ID!
        name: String!
        email: String! @cacheControl(scope: PRIVATE)
    }
"""

query = QueryType()

@query.field("users")
async def resolve_users(*_):
    return [{"id": "1", "name": "Alice", "email": "alice@example.com"}]

@query.field("me")
async def resolve_me(*_):
    return {"id": "1", "name": "Alice", "email": "alice@example.com"}

schema = make_executable_schema(type_defs, query)

# Create cache service
config = CacheConfig(
    enabled=True,
    use_cache_control=True,
    default_max_age=0,  # No cache by default (conservative)
    calculate_http_headers=True,
    cache_queries=True,
    cache_mutations=False,
)
cache_service = CacheService(
    backend=InMemoryCacheBackend(maxsize=1000),
    key_builder=DefaultKeyBuilder(),
    serializer=JsonSerializer(),
    config=config,
)

# Create the GraphQL app with caching
graphql_app = CachingGraphQL(
    schema,
    cache_service=cache_service,
    debug=True,
)

# Mount on FastAPI
app = FastAPI()
app.mount("/graphql", graphql_app)
```

## Cache Control Semantics

Following Apollo Server's rules:

### Response Policy Calculation

The overall cache policy is determined by the **most restrictive** values:

- **maxAge**: Uses the **lowest** value across all fields
- **scope**: Uses **PRIVATE** if any field specifies PRIVATE

### Default Behavior

- Root fields (Query, Mutation): Default `maxAge: 0` (no caching)
- Object/Interface/Union fields: Default `maxAge: 0`
- Scalar fields: Inherit from parent

This conservative approach ensures only explicitly cacheable data gets cached.

### HTTP Headers

cacheql automatically generates `Cache-Control` headers:

```
Cache-Control: max-age=300, public
Cache-Control: max-age=60, private
Cache-Control: no-store  (when maxAge is 0)
```

## Dynamic Cache Hints in Resolvers

Set cache hints dynamically based on runtime conditions:

```python
from cacheql.hints import set_cache_hint, private_cache, no_cache

@query.field("user")
async def resolve_user(_, info, id: str):
    user = await get_user(id)

    # Set cache hint based on user data
    if user.is_public_profile:
        set_cache_hint(info, max_age=3600, scope="PUBLIC")
    else:
        set_cache_hint(info, max_age=60, scope="PRIVATE")

    return user

@query.field("sensitive_data")
async def resolve_sensitive(_, info):
    # Disable caching entirely
    no_cache(info)
    return get_sensitive_data()

@query.field("my_profile")
async def resolve_my_profile(_, info):
    # Shorthand for private cache
    private_cache(info, max_age=300)
    return get_current_user_profile(info)
```

## Legacy Mode (Simple TTL-based Caching)

For simpler use cases without directive parsing:

```python
from datetime import timedelta
from cacheql import CacheConfig

config = CacheConfig(
    use_cache_control=False,  # Disable directive parsing
    default_ttl=timedelta(minutes=5),
)

# All queries are cached with the default TTL
```

## Field-Level Caching with Decorators

For fine-grained control without schema directives:

```python
from cacheql import cached, invalidates, configure

configure(cache_service)

@cached(ttl=timedelta(minutes=10), tags=["User", "User:{id}"])
async def get_user(id: str) -> dict:
    return await db.get_user(id)

@invalidates(tags=["User", "User:{id}"])
async def update_user(id: str, data: dict) -> dict:
    return await db.update_user(id, data)
```

## Redis Backend

For distributed deployments:

```python
from cacheql_redis import RedisCacheBackend

backend = RedisCacheBackend(
    redis_url="redis://localhost:6379",
    key_prefix="myapp",
)

cache_service = CacheService(
    backend=backend,
    key_builder=DefaultKeyBuilder(),
    serializer=JsonSerializer(),
    config=config,
)
```

## Configuration

```python
from datetime import timedelta
from cacheql import CacheConfig

config = CacheConfig(
    enabled=True,                           # Enable/disable caching
    default_ttl=timedelta(minutes=5),       # Default TTL (legacy mode)
    max_size=1000,                          # Max entries for LRU backends
    key_prefix="cacheql",                   # Prefix for cache keys

    # Cache control settings (Apollo-style)
    use_cache_control=True,                 # Enable directive parsing
    default_max_age=0,                      # Default maxAge in seconds
    calculate_http_headers=True,            # Generate Cache-Control headers

    # Query behavior
    cache_queries=True,                     # Cache query responses
    cache_mutations=False,                  # Don't cache mutations
    auto_invalidate_on_mutation=True,       # Auto-invalidate on mutations
)
```

## Accessing Cache Statistics

You can access cache statistics through the GraphQL app:

```python
graphql_app = CachingGraphQL(schema, cache_service=cache_service)

# Access statistics
stats = graphql_app.cache_stats
print(f"Hits: {stats['hits']}")
print(f"Misses: {stats['misses']}")

# Or directly from the cache service
stats = cache_service.stats
```

## Cache Invalidation

### By Tags

```python
await cache_service.invalidate(["User"])
await cache_service.invalidate(["User:123"])
```

### Clear All

```python
await cache_service.clear()
```

## HTTP Headers

When using `CachingGraphQL`, cache control headers are automatically set on responses:

- `Cache-Control: max-age=300, public` - for cacheable responses
- `Cache-Control: max-age=60, private` - for private responses
- `Cache-Control: no-store` - when maxAge is 0
- `X-Cache: HIT` - indicates response was served from cache

To read these headers in middleware (e.g., with FastAPI):

```python
from starlette.middleware.base import BaseHTTPMiddleware

class CacheHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)

        # Read headers set by CachingGraphQL
        cache_header = getattr(request.state, "cache_control_header", None)
        if cache_header:
            response.headers["Cache-Control"] = cache_header

        if getattr(request.state, "cache_hit", False):
            response.headers["X-Cache"] = "HIT"

        return response

app.add_middleware(CacheHeaderMiddleware)
```

## Architecture

cacheql follows Domain-Driven Design principles:

```
┌─────────────────────────────────────────────┐
│         Adapters (Ariadne/Strawberry)       │
├─────────────────────────────────────────────┤
│         Application Services                │
├─────────────────────────────────────────────┤
│         Domain (Core)                       │
├─────────────────────────────────────────────┤
│         Infrastructure                      │
└─────────────────────────────────────────────┘
```

### Core Components

- `CacheHint`: Represents cache control settings (maxAge, scope)
- `CacheScope`: Enum for PUBLIC/PRIVATE scope
- `ResponseCachePolicy`: Calculated policy for entire response
- `CacheControlCalculator`: Calculates policy from hints
- `DirectiveParser`: Parses @cacheControl from schema

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=cacheql --cov-report=html

# Type checking
mypy src/cacheql

# Linting
ruff check src/cacheql
```

## License

MIT License - see LICENSE file for details.
