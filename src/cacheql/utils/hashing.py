"""Hashing utilities for cache key generation."""

import hashlib
import json
from typing import Any


def hash_value(value: Any) -> str:
    """Create a deterministic hash of a value.

    Args:
        value: Any JSON-serializable value.

    Returns:
        A hexadecimal hash string (first 16 chars of SHA-256).
    """
    if value is None:
        return "none"

    # Normalize to JSON with sorted keys for determinism
    normalized = json.dumps(value, sort_keys=True, default=str)
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


def normalize_query(query: str) -> str:
    """Normalize a GraphQL query string for consistent hashing.

    Removes extra whitespace and normalizes formatting to ensure
    equivalent queries produce the same hash.

    Args:
        query: The GraphQL query string.

    Returns:
        The normalized query string.
    """
    # Simple normalization: collapse whitespace
    return " ".join(query.split())
