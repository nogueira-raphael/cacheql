# FastAPI + Strawberry + Redis Example

This example demonstrates how to use **cacheql** with [Strawberry GraphQL](https://strawberry.rocks/) and FastAPI, using Redis as the cache backend.

## Features

- Strawberry GraphQL schema with type-safe Python classes
- Dynamic cache hints in resolvers using `set_cache_hint()`, `private_cache()`, `no_cache()`
- Cache invalidation on mutations
- Redis backend for distributed caching
- Docker Compose setup for easy deployment

## Quick Start

### Using Docker Compose (Recommended)

```bash
docker-compose up --build
```

The GraphQL playground will be available at http://localhost:8000/graphql

> **Note:** Docker Compose mounts `cacheql` and `cacheql_redis` from the parent repository. This example is designed to run from within the cacheql repository.

### Manual Setup

1. Install cacheql from the repository root:

```bash
# From repository root
pip install -e .
pip install -e extras/redis
```

2. Install example dependencies:

```bash
cd examples/fastapi-strawberry-redis
pip install -r requirements.txt
```

3. Start Redis:

```bash
docker run -d -p 6379:6379 redis:7-alpine
```

4. Run the application:

```bash
uvicorn app.main:app --reload
```

## Project Structure

```
.
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI app with Strawberry
│   ├── schema.py        # Strawberry schema with cache hints
│   └── database.py      # SQLite database for demo
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Example Queries

### Get all users (cached for 5 minutes)

```graphql
query {
  users {
    id
    name
    email
  }
}
```

### Get current user (private cache, 1 minute)

```graphql
query {
  me {
    id
    name
    email
    secretNote
  }
}
```

### Get a user with dynamic caching

```graphql
query {
  user(id: "1") {
    id
    name
    isPublicProfile
  }
}
```

Public profiles are cached for 1 hour, private profiles for 1 minute with private scope.

### Get posts (cached for 5 minutes)

```graphql
query {
  posts {
    id
    title
    author {
      name
    }
  }
}
```

### Check database call statistics (never cached)

```graphql
query {
  dbStats {
    getUsersCalls
    getUserCalls
    getPostsCalls
  }
}
```

## Mutations with Cache Invalidation

### Update a user

```graphql
mutation {
  updateUser(id: "1", name: "Alice Updated") {
    id
    name
  }
}
```

This mutation automatically invalidates `User` and `User:1` cache tags.

### Create a post

```graphql
mutation {
  createPost(title: "New Post", content: "Content here", authorId: "1") {
    id
    title
  }
}
```

## Cache Control in Resolvers

The example uses dynamic cache hints in resolvers:

```python
@strawberry.field
async def users(self, info: Info) -> list[User]:
    # Cache for 5 minutes, public
    set_cache_hint(info, max_age=300, scope="PUBLIC")
    return await db.get_users()

@strawberry.field
async def me(self, info: Info) -> Optional[User]:
    # Private cache for 1 minute
    private_cache(info, max_age=60)
    return await db.get_current_user()

@strawberry.field
async def db_stats(self, info: Info) -> DbStats:
    # Never cache this field
    no_cache(info)
    return get_stats()
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/graphql` | GET/POST | GraphQL endpoint with playground |
| `/health` | GET | Health check with Redis status |
| `/cache/stats` | GET | Cache hit/miss statistics |
| `/cache/clear` | POST | Clear all cached entries |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `DEBUG` | `false` | Enable debug logging |
