"""Tests for JsonSerializer."""

from datetime import date, datetime

import pytest

from cacheql.infrastructure.serializers.json import JsonSerializer, SerializationError


class TestJsonSerializer:
    """Tests for JsonSerializer."""

    @pytest.fixture
    def serializer(self) -> JsonSerializer:
        """Create a serializer for testing."""
        return JsonSerializer()

    def test_serialize_dict(self, serializer: JsonSerializer) -> None:
        """Test serializing a dictionary."""
        data = {"name": "Alice", "age": 30}
        result = serializer.serialize(data)

        assert isinstance(result, bytes)
        assert b"Alice" in result
        assert b"30" in result

    def test_deserialize_dict(self, serializer: JsonSerializer) -> None:
        """Test deserializing to a dictionary."""
        data = b'{"name": "Alice", "age": 30}'
        result = serializer.deserialize(data)

        assert result == {"name": "Alice", "age": 30}

    def test_roundtrip(self, serializer: JsonSerializer) -> None:
        """Test serialization roundtrip."""
        original = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"},
            ],
            "count": 2,
        }

        serialized = serializer.serialize(original)
        deserialized = serializer.deserialize(serialized)

        assert deserialized == original

    def test_serialize_list(self, serializer: JsonSerializer) -> None:
        """Test serializing a list."""
        data = [1, 2, 3, "four"]
        result = serializer.serialize(data)
        deserialized = serializer.deserialize(result)

        assert deserialized == data

    def test_serialize_nested(self, serializer: JsonSerializer) -> None:
        """Test serializing nested structures."""
        data = {
            "level1": {
                "level2": {
                    "level3": ["a", "b", "c"]
                }
            }
        }
        result = serializer.serialize(data)
        deserialized = serializer.deserialize(result)

        assert deserialized == data

    def test_serialize_datetime(self, serializer: JsonSerializer) -> None:
        """Test serializing datetime objects."""
        dt = datetime(2024, 1, 15, 10, 30, 0)
        data = {"timestamp": dt}

        result = serializer.serialize(data)
        deserialized = serializer.deserialize(result)

        assert "__datetime__" in deserialized["timestamp"]

    def test_serialize_date(self, serializer: JsonSerializer) -> None:
        """Test serializing date objects."""
        d = date(2024, 1, 15)
        data = {"date": d}

        result = serializer.serialize(data)
        deserialized = serializer.deserialize(result)

        assert "__date__" in deserialized["date"]

    def test_serialize_none(self, serializer: JsonSerializer) -> None:
        """Test serializing None."""
        result = serializer.serialize(None)
        deserialized = serializer.deserialize(result)

        assert deserialized is None

    def test_deserialize_invalid_json(self, serializer: JsonSerializer) -> None:
        """Test deserializing invalid JSON raises error."""
        with pytest.raises(SerializationError):
            serializer.deserialize(b"not valid json")

    def test_deserialize_invalid_encoding(self, serializer: JsonSerializer) -> None:
        """Test deserializing invalid encoding raises error."""
        with pytest.raises(SerializationError):
            serializer.deserialize(b"\xff\xfe")

    def test_serialize_non_serializable(self, serializer: JsonSerializer) -> None:
        """Test serializing objects with circular references raises error."""
        # Circular references can't be serialized
        circular: dict = {}
        circular["self"] = circular
        with pytest.raises(SerializationError):
            serializer.serialize(circular)

    def test_custom_encoding(self) -> None:
        """Test serializer with custom encoding."""
        serializer = JsonSerializer(encoding="utf-16")
        data = {"name": "Alice"}

        result = serializer.serialize(data)
        deserialized = serializer.deserialize(result)

        assert deserialized == data
