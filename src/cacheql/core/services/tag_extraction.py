"""Derive cache invalidation tags from GraphQL response data.

Walks response data and, for every object it can identify a GraphQL
type for, emits a ``TypeName`` tag and - when an ``id`` field is
present - a ``TypeName:id`` tag. This lets ``CacheService.invalidate``
target cached responses by type without callers having to pass
explicit ``tags=`` on every ``cache_response`` call.

Type identification prefers ``__typename`` when the response includes
it (always true for the client), and otherwise falls back to a
``type_info`` mapping built via :mod:`cacheql.core.services.type_info`.
"""

from typing import Any


def extract_response_tags(
    data: Any,
    type_info: dict[str, str] | None = None,
) -> list[str]:
    """Collect ``TypeName``/``TypeName:id`` tags from response data.

    Args:
        data: A GraphQL response's ``data`` payload (or any sub-tree).
        type_info: Optional mapping of response field paths to type
            names, used when ``__typename`` is absent from the data.

    Returns:
        A de-duplicated, order-preserving list of tags.
    """
    tags: list[str] = []
    seen: set[str] = set()

    def add(tag: str) -> None:
        if tag not in seen:
            seen.add(tag)
            tags.append(tag)

    _walk(data, path=[], type_info=type_info or {}, add=add)
    return tags


def _walk(
    data: Any,
    path: list[str],
    type_info: dict[str, str],
    add: Any,
) -> None:
    if isinstance(data, dict):
        path_str = ".".join(path)
        type_name = data.get("__typename") or type_info.get(path_str)

        if type_name:
            add(type_name)
            entry_id = data.get("id")
            if entry_id is not None:
                add(f"{type_name}:{entry_id}")

        for field_name, field_value in data.items():
            if field_name == "__typename":
                continue
            _walk(field_value, [*path, field_name], type_info, add)

    elif isinstance(data, list):
        for item in data:
            _walk(item, path, type_info, add)
