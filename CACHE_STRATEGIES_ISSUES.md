# CacheQL: GraphQL Caching Strategies

This document describes the caching strategies implemented in CacheQL, based on best practices from the GraphQL community.

---

## References

This project follows specifications and recommendations from:

1. **[Apollo Server - Caching](https://www.apollographql.com/docs/apollo-server/performance/caching/)**
   - `@cacheControl` directive semantics
   - Cache policy calculation (minimum maxAge, restrictive scope)
   - HTTP Cache-Control header generation

2. **[GraphQL.js - Caching Strategies](https://www.graphql-js.org/docs/caching-strategies/)**
   - Resolver-level caching
   - Operation result caching
   - Cache invalidation strategies

3. **[GraphQL Official Documentation](https://graphql.org/learn/caching/)**
   - Fundamental concepts of caching in GraphQL
   - Globally unique IDs for invalidation

---

## Implemented Strategies

### 1. Resolver-Level Caching ✅

Cache the result of specific fields via the `@cached` decorator.

```python
from cacheql import cached
from datetime import timedelta

@cached(ttl=timedelta(minutes=10), tags=["User", "User:{id}"])
async def get_user(id: str) -> dict:
    return await db.get_user(id)
```

**Reference**: [GraphQL.js - Resolver-level caching](https://www.graphql-js.org/docs/caching-strategies/#resolver-level-caching)

---

### 2. Operation Result Caching ✅

Cache the complete response of GraphQL queries, identified by query + variables.

```python
from cacheql import CacheService, CacheConfig

config = CacheConfig(
    cache_queries=True,
    use_cache_control=True,
)
```

**Features**:
- Cache key: SHA-256 hash of query + variables
- Supports InMemory and Redis backends
- Respects `@cacheControl` directives from schema

**Reference**: [GraphQL.js - Operation result caching](https://www.graphql-js.org/docs/caching-strategies/#operation-result-caching)

---

### 3. Cache Invalidation ✅

Cache invalidation via automatic TTL and manual tags.

```python
# Invalidation by tags
await cache_service.invalidate(["User", "User:123"])

# Invalidation by type
await cache_service.invalidate_by_type("User")

# Clear all cache
await cache_service.clear()
```

**Supported strategies**:
- **TTL**: Automatic expiration after configured time
- **Manual Purging**: Removal by tags when updating data
- **Auto-invalidation**: Automatic invalidation on mutations

**Reference**: [GraphQL.js - Cache invalidation](https://www.graphql-js.org/docs/caching-strategies/#cache-invalidation)

---

### 4. Apollo-Style Cache Control ✅

Full support for Apollo Server's `@cacheControl` directive.

```graphql
type Query {
  users: [User!]! @cacheControl(maxAge: 300)
  me: User @cacheControl(maxAge: 60, scope: PRIVATE)
}

type User @cacheControl(maxAge: 600) {
  id: ID!
  name: String!
  email: String! @cacheControl(scope: PRIVATE)
}
```

**Aggregation rules**:
- `maxAge`: uses the **lowest value** among all fields
- `scope`: uses **PRIVATE** if any field is PRIVATE

**Reference**: [Apollo Server - @cacheControl](https://www.apollographql.com/docs/apollo-server/performance/caching/#in-your-schema-static)

---

### 5. HTTP Cache Headers ✅

Automatic generation of HTTP Cache-Control headers.

```
Cache-Control: max-age=300, public
Cache-Control: max-age=60, private
Cache-Control: no-store
```

**Reference**: [Apollo Server - HTTP caching](https://www.apollographql.com/docs/apollo-server/performance/caching/#http-caching)

---

## Roadmap

### Issue #12: Context-Aware Cache Keys

**Objective**: Allow including HTTP headers (Authorization, Accept-Language) in the cache key.

**Phase 1 - Minimal Implementation**:
- [ ] Add field `cache_key_headers: list[str]` to CacheConfig
- [ ] Modify DefaultKeyBuilder to extract headers from context
- [ ] Basic unit tests

**Phase 2 - Expansion**:
- [ ] Customizable context extractor
- [ ] Support for normalized headers (case-insensitive)
- [ ] Documentation and examples

**Files**:
- `src/cacheql/core/entities/cache_config.py`
- `src/cacheql/infrastructure/key_builders/default.py`

**GitHub**: https://github.com/nogueira-raphael/cacheql/issues/12

---

### Issue #13: Stale-While-Revalidate

**Objective**: Serve expired data while revalidating in the background.

**Phase 1 - Minimal Implementation**:
- [ ] Add field `stale_while_revalidate: int | None` to CacheHint
- [ ] Backend stores expiration timestamp separately from TTL
- [ ] Return stale data and mark for revalidation
- [ ] Basic unit tests

**Phase 2 - Expansion**:
- [ ] Add `staleWhileRevalidate` to `@cacheControl` directive
- [ ] Async background revalidation task
- [ ] HTTP header `stale-while-revalidate`
- [ ] Redis backend support

**Files**:
- `src/cacheql/core/entities/cache_control.py`
- `src/cacheql/core/services/cache_service.py`
- `src/cacheql/infrastructure/backends/memory.py`

**GitHub**: https://github.com/nogueira-raphael/cacheql/issues/13

---

## Out of Scope

| Strategy | Reason |
|----------|--------|
| Schema Cache | Framework responsibility (Strawberry/Ariadne) |
| Client Cache | Client responsibility (Apollo Client, Relay, URQL) |
| DataLoader/N+1 | Separate pattern, not traditional caching |

---

## Useful Links

- [CacheQL Repository](https://github.com/nogueira-raphael/cacheql)
- [Apollo Server Caching Docs](https://www.apollographql.com/docs/apollo-server/performance/caching/)
- [GraphQL.js Caching Strategies](https://www.graphql-js.org/docs/caching-strategies/)
- [HTTP Caching - MDN](https://developer.mozilla.org/en-US/docs/Web/HTTP/Caching)
