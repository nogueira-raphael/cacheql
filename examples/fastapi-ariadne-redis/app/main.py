"""FastAPI + Ariadne + cacheql example."""

import os
from contextlib import asynccontextmanager
from typing import Any

from ariadne import make_executable_schema
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app.resolvers import resolvers
from app.schema import TYPE_DEFS
from app import database as db

from cacheql import CacheConfig, CacheService, DefaultKeyBuilder, JsonSerializer
from cacheql.adapters.ariadne import CachingGraphQL
from cacheql_redis import RedisCacheBackend

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
DEBUG = os.getenv("DEBUG", "false").lower() == "true"

# Cache setup
cache_config = CacheConfig(
    enabled=True,
    use_cache_control=True,
    default_max_age=0,
    calculate_http_headers=True,
    key_prefix="example",
    cache_queries=True,
    cache_mutations=False,
    session_context_keys=["current_user_id"],
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

schema = make_executable_schema(TYPE_DEFS, *resolvers)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[STARTUP] Initializing SQLite database")
    await db.init_db()
    print(f"[STARTUP] Connecting to Redis at {REDIS_URL}")
    yield
    print("[SHUTDOWN] Closing Redis connection")
    await cache_backend.close()


app = FastAPI(
    title="cacheql Example API",
    description="GraphQL API with cacheql caching",
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


class CacheControlMiddleware(BaseHTTPMiddleware):
    """Adds Cache-Control and X-Cache headers to responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        cache_header = getattr(request.state, "cache_control_header", None)
        if cache_header:
            response.headers["Cache-Control"] = cache_header

        if getattr(request.state, "cache_hit", False):
            response.headers["X-Cache"] = "HIT"

        return response


app.add_middleware(CacheControlMiddleware)


def get_context_value(request: Request) -> dict[str, Any]:
    auth = request.headers.get("Authorization", "")
    current_user_id = None
    if auth.startswith("Bearer user-"):
        current_user_id = auth.removeprefix("Bearer user-")

    return {
        "request": request,
        "cache_service": cache_service,
        "current_user_id": current_user_id,
    }


def should_cache(data: dict[str, Any]) -> bool:
    """Skip caching for debug queries."""
    query = data.get("query", "")
    return "dbStats" not in query


graphql_app = CachingGraphQL(
    schema,
    cache_service=cache_service,
    should_cache=should_cache,
    debug=DEBUG,
    context_value=get_context_value,
    execute_get_queries=True,
)

app.mount("/graphql", graphql_app)


@app.get("/health")
async def health_check():
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
    await cache_service.clear()
    return {"status": "cleared"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
