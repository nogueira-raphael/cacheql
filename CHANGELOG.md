# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.0.1a3] - 2026-08-13

### Added
- Scope-aware caching with `session_id` callback in Ariadne adapter (Apollo-style)
- Dual cache lookup: private key first (per-user), then public key (shared)
- PUBLIC responses cached with shared key; PRIVATE responses cached per-user; PRIVATE without session_id skipped
- `cacheql.core.services.type_info.build_type_info`: resolves response field paths to GraphQL type names from the query AST + schema, independent of whether the client requested `__typename`
- `cacheql.core.services.tag_extraction.extract_response_tags`: derives `TypeName`/`TypeName:id` invalidation tags from response data
- `ICacheBackend.keys(pattern)`, implemented by `InMemoryCacheBackend` and `RedisCacheBackend`
- Ariadne adapter now auto-invalidates cache entries on successful mutations (`auto_invalidate_on_mutation`), matching the Strawberry adapter's existing behavior
- Ariadne and Strawberry adapters now auto-tag cached responses so `cache_service.invalidate([...])`/`@cached(tags=[...])` work against whole-query caches without callers passing `tags=` explicitly

### Fixed
- `CacheService.invalidate()` only deleted its own tag-index bookkeeping entries and left the actual cached response/field data in place; it now resolves the index back to the real cache key and deletes both. This affected `@cached`/`@invalidates` decorators and `cache_service.invalidate()` for both adapters.
- `@cacheControl` type-level and field-level directives on nested object types were silently ignored unless the client's query happened to request `__typename` (the calculator had no other way to know a field's GraphQL type). The Ariadne adapter now resolves field types from the query AST + schema via `build_type_info`.
- `InMemoryCacheBackend` accepted a per-item `ttl` on `set()` but ignored it, applying a single global TTL to every entry (`cachetools.TTLCache` doesn't support per-item TTL). It now tracks per-item expiry, so `@cacheControl(maxAge: ...)` is honored by the default backend, not just the Redis one.
- `set_cache_hint`/`private_cache`/`no_cache` (`cacheql.hints`) silently did nothing when called from resolvers - the `CacheControlContext` they write to was never created or injected into the request context. The Ariadne adapter now injects it before execution.
- `cacheql.__version__` was a hardcoded literal that had drifted from the version in `pyproject.toml`; it's now read from installed package metadata.

### Changed
- `session_id` callback replaces `session_context_keys` for session identity (moved from config to adapter layer)
- `CacheService.invalidate()` no longer falls back to matching tags as a raw substring against all cache keys (`key_prefix:*{tag}*`); invalidation is now exclusively tag-index based, which is precise and no longer depends on the tag string happening to appear inside an unrelated key.

### Removed
- `session_context_keys` field from `CacheConfig` (use `session_id` callback on `CachingGraphQL`/`CachingGraphQLHTTPHandler` instead)

## [0.0.1a2] - 2026-02-15

### Added
- Context-aware cache keys via `session_context_keys` in `CacheConfig` (#12)
- Ariadne and Strawberry adapters extract configured keys from GraphQL context for per-user cache isolation
- Fake token auth (`Authorization: Bearer user-{id}`) in Ariadne example for PRIVATE cache testing
- Unit tests for Ariadne handler context extraction
- Unit tests for Strawberry extension context extraction
- Integration test for per-user cache isolation in Ariadne handler
- Unit tests for Ariadne decorators
- Unit tests for Strawberry extension
- Cache control documentation in Ariadne example

### Fixed
- Ariadne handler now resolves `context_value` before cache lookup (was `None`, causing all users to share the same cache key)

### Removed
- `CacheHint.to_http_header()` method (unused; HTTP header generation is handled by `ResponseCachePolicy.to_http_header()`)
- Deprecated `CacheExtension` and `create_cache_extension` from Ariadne adapter (use `CachingGraphQL` instead)

## [0.0.1a1] - 2026-02-06

### Added
- Makefile with common development tasks
- Coverage configuration in pyproject.toml
- Caching Strategies documentation in README
- Project badges (codecov, PyPI version, downloads, Python version)
- Codecov integration in CI workflow
- `CACHE_STRATEGIES_ISSUES.md` with implementation roadmap

### Changed
- Expanded mypy configuration with dependency overrides
- Added ruff isort configuration

### Fixed
- Removed unused type ignore comment in memory backend

## [0.0.1a0] - 2026-02-06

### Added
- Initial alpha release
- Apollo-style `@cacheControl` directive support
- Query-level caching with CacheService
- Field-level caching with `@cached` decorator
- In-memory backend (LRU with TTL)
- Redis backend support
- Ariadne adapter (CachingGraphQL)
- Strawberry adapter (CacheExtension)
- Tag-based cache invalidation
- Dynamic cache hints in resolvers
- HTTP Cache-Control header generation
- FastAPI + Ariadne + Redis example
- FastAPI + Strawberry + Redis example

[Unreleased]: https://github.com/nogueira-raphael/cacheql/compare/v0.0.1a2...HEAD
[0.0.1a2]: https://github.com/nogueira-raphael/cacheql/compare/v0.0.1a1...v0.0.1a2
[0.0.1a1]: https://github.com/nogueira-raphael/cacheql/compare/v0.0.1a0...v0.0.1a1
[0.0.1a0]: https://github.com/nogueira-raphael/cacheql/releases/tag/v0.0.1a0
