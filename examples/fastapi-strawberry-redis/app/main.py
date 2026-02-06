"""FastAPI + Strawberry + cacheql example."""

import os
from contextlib import asynccontextmanager
from typing import Any

import strawberry
from cacheql_redis import RedisCacheBackend
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter

from app import database as db
from app.schema import Mutation, Query
from cacheql import CacheConfig, CacheService, DefaultKeyBuilder, JsonSerializer
from cacheql.adapters.strawberry import CacheExtension

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Cache configuration
cache_config = CacheConfig(
    enabled=True,
    use_cache_control=True,
    default_max_age=0,
    calculate_http_headers=True,
    key_prefix="strawberry-example",
    cache_queries=True,
    cache_mutations=False,
)

cache_backend = RedisCacheBackend(
    redis_url=REDIS_URL,
    key_prefix="cacheql:strawberry",
)

cache_service = CacheService(
    backend=cache_backend,
    key_builder=DefaultKeyBuilder(),
    serializer=JsonSerializer(),
    config=cache_config,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    print("[STARTUP] Initializing SQLite database")
    await db.init_db()
    print(f"[STARTUP] Connecting to Redis at {REDIS_URL}")
    yield
    print("[SHUTDOWN] Closing Redis connection")
    await cache_backend.close()


app = FastAPI(
    title="cacheql Strawberry Example",
    description="GraphQL API with Strawberry and cacheql caching",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def get_context(request: Request) -> dict[str, Any]:
    """Get GraphQL context with cache service."""
    return {
        "request": request,
        "cache_service": cache_service,
    }


# Create cache extension
cache_extension = CacheExtension(cache_service)

# Create schema with cache extension
schema = strawberry.Schema(
    query=Query,
    mutation=Mutation,
    extensions=[cache_extension],
)

# Create GraphQL router
graphql_app = GraphQLRouter(
    schema,
    context_getter=get_context,
)

app.include_router(graphql_app, prefix="/graphql")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        await cache_backend._redis.ping()
        redis_status = "healthy"
    except Exception as e:
        redis_status = f"unhealthy: {e}"

    return {
        "status": "healthy",
        "redis": redis_status,
        "cache_enabled": cache_config.enabled,
    }


@app.get("/cache/stats")
async def cache_stats():
    """Get cache statistics."""
    return {
        "stats": cache_service.stats,
        "config": {
            "enabled": cache_config.enabled,
            "use_cache_control": cache_config.use_cache_control,
            "default_max_age": cache_config.default_max_age,
            "key_prefix": cache_config.key_prefix,
        },
    }


@app.post("/cache/clear")
async def clear_cache():
    """Clear the cache."""
    await cache_service.clear()
    return {"status": "cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
