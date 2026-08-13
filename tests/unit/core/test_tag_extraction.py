"""Tests for extract_response_tags."""

from cacheql.core.services.tag_extraction import extract_response_tags


class TestExtractResponseTags:
    def test_no_type_info_or_typename_yields_no_tags(self) -> None:
        data = {"user": {"id": "1", "name": "Alice"}}
        assert extract_response_tags(data) == []

    def test_uses_typename_when_present(self) -> None:
        data = {"user": {"__typename": "User", "id": "1", "name": "Alice"}}
        tags = extract_response_tags(data)
        assert tags == ["User", "User:1"]

    def test_uses_type_info_when_typename_absent(self) -> None:
        data = {"user": {"id": "1", "name": "Alice"}}
        type_info = {"user": "User"}
        tags = extract_response_tags(data, type_info)
        assert tags == ["User", "User:1"]

    def test_typename_takes_precedence_over_type_info(self) -> None:
        data = {"user": {"__typename": "Admin", "id": "1"}}
        type_info = {"user": "User"}
        tags = extract_response_tags(data, type_info)
        assert "Admin" in tags
        assert "Admin:1" in tags
        assert "User" not in tags

    def test_object_without_id_only_gets_type_tag(self) -> None:
        data = {"stats": {"__typename": "Stats", "count": 5}}
        tags = extract_response_tags(data)
        assert tags == ["Stats"]

    def test_walks_lists(self) -> None:
        data = {
            "users": [
                {"__typename": "User", "id": "1"},
                {"__typename": "User", "id": "2"},
            ]
        }
        tags = extract_response_tags(data)
        assert tags == ["User", "User:1", "User:2"]

    def test_walks_nested_objects(self) -> None:
        data = {
            "post": {
                "__typename": "Post",
                "id": "10",
                "author": {"__typename": "User", "id": "1"},
            }
        }
        tags = extract_response_tags(data)
        assert tags == ["Post", "Post:10", "User", "User:1"]

    def test_deduplicates_tags(self) -> None:
        data = {
            "a": {"__typename": "User", "id": "1"},
            "b": {"__typename": "User", "id": "1"},
        }
        tags = extract_response_tags(data)
        assert tags == ["User", "User:1"]

    def test_none_data_yields_no_tags(self) -> None:
        assert extract_response_tags(None) == []

    def test_scalar_data_yields_no_tags(self) -> None:
        assert extract_response_tags("just a string") == []
