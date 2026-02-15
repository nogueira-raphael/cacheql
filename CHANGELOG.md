# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/nogueira-raphael/cacheql/compare/v0.0.1a1...HEAD
[0.0.1a1]: https://github.com/nogueira-raphael/cacheql/compare/v0.0.1a0...v0.0.1a1
[0.0.1a0]: https://github.com/nogueira-raphael/cacheql/releases/tag/v0.0.1a0
