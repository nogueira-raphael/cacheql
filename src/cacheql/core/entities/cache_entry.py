"""Cache entry entity."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


@dataclass(frozen=True)
class CacheEntry:
    """Immutable cache entry value object.

    Represents a cached value with associated metadata including
    creation time, TTL, tags for invalidation, and custom metadata.
    """

    key: str
    value: Any
    created_at: datetime
    ttl: timedelta | None = None
    tags: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def expires_at(self) -> datetime | None:
        """Calculate expiration time.

        Returns:
            The datetime when this entry expires, or None if no TTL.
        """
        if self.ttl is None:
            return None
        return self.created_at + self.ttl

    @property
    def is_expired(self) -> bool:
        """Check if entry has expired.

        Returns:
            True if the entry has expired, False otherwise.
        """
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    @classmethod
    def create(
        cls,
        key: str,
        value: Any,
        ttl: timedelta | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "CacheEntry":
        """Factory method to create a new cache entry.

        Args:
            key: The cache key.
            value: The value to cache.
            ttl: Optional time-to-live.
            tags: Optional list of tags for invalidation.
            metadata: Optional custom metadata.

        Returns:
            A new CacheEntry instance.
        """
        return cls(
            key=key,
            value=value,
            created_at=datetime.now(timezone.utc),
            ttl=ttl,
            tags=tuple(tags) if tags else (),
            metadata=metadata or {},
        )
