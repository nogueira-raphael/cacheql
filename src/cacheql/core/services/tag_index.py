"""Key format for the tag -> cache key invalidation index.

A tag index entry maps one tag to one cache key, stored under a key of
its own so ``CacheService.invalidate`` can look it up and delete both.
Tags routinely contain colons (``"User:123"``), so a plain ``:`` can't
also be the delimiter between the tag and the cache key it points at:
invalidating ``"User:1"`` would then glob-match an index entry for the
unrelated tag ``"User:10"`` too, since ``"User:10"`` starts with
``"User:1"``. A separator that can't appear in a normal tag closes that
ambiguity.
"""

_SEPARATOR = "\x1e"


def build_tag_index_key(prefix: str, tag: str, cache_key: str) -> str:
    """Build the storage key for one tag -> cache key mapping."""
    return f"{prefix}:tag:{tag}{_SEPARATOR}{cache_key}"


def tag_index_pattern(prefix: str, tag: str) -> str:
    """Build the glob pattern matching all mappings for a given tag."""
    return f"{prefix}:tag:{tag}{_SEPARATOR}*"
