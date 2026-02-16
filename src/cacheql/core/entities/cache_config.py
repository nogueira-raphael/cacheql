"""Cache configuration entity."""

from dataclasses import dataclass
from datetime import timedelta


@dataclass
class CacheConfig:
    """Cache configuration.

    Provides configuration options for the caching system,
    including TTL defaults, size limits, and feature toggles.

    Cache Control Mode (Apollo-style):
        When use_cache_control=True, the library follows Apollo Server's
        @cacheControl directive semantics. Cache decisions are based on
        schema directives and the most restrictive policy applies.

    Legacy Mode:
        When use_cache_control=False, uses simple TTL-based caching
        with the default_ttl value.
    """

    enabled: bool = True
    default_ttl: timedelta | None = None
    max_size: int | None = 1000
    key_prefix: str = "cacheql"

    # Query-level settings
    cache_queries: bool = True
    cache_mutations: bool = False

    # Field-level settings
    cache_fields: bool = False

    # Invalidation
    auto_invalidate_on_mutation: bool = True

    # Cache Control (Apollo-style) settings
    use_cache_control: bool = True
    default_max_age: int = 0  # Default maxAge in seconds (0 = no cache by default)
    calculate_http_headers: bool = True  # Generate Cache-Control HTTP headers

    def __post_init__(self) -> None:
        """Set default TTL if not provided."""
        if self.default_ttl is None:
            self.default_ttl = timedelta(minutes=5)
