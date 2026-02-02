"""JSON serializer implementation."""

import json
from datetime import date, datetime
from typing import Any


class SerializationError(Exception):
    """Raised when serialization or deserialization fails."""

    pass


class JsonSerializer:
    """JSON serializer for cache values.

    Handles serialization of Python objects to JSON bytes
    and deserialization back to Python objects.
    """

    def __init__(self, encoding: str = "utf-8") -> None:
        """Initialize the JSON serializer.

        Args:
            encoding: Character encoding to use.
        """
        self._encoding = encoding

    def serialize(self, value: Any) -> bytes:
        """Serialize value to bytes.

        Args:
            value: The Python object to serialize.

        Returns:
            The serialized value as bytes.

        Raises:
            SerializationError: If the value cannot be serialized.
        """
        try:
            json_str = json.dumps(value, default=self._default_encoder)
            return json_str.encode(self._encoding)
        except (TypeError, ValueError) as e:
            raise SerializationError(f"Failed to serialize value: {e}") from e

    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to value.

        Args:
            data: The bytes to deserialize.

        Returns:
            The deserialized Python object.

        Raises:
            SerializationError: If the data cannot be deserialized.
        """
        try:
            json_str = data.decode(self._encoding)
            return json.loads(json_str)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            raise SerializationError(f"Failed to deserialize data: {e}") from e

    def _default_encoder(self, obj: Any) -> Any:
        """Custom encoder for non-JSON-serializable types.

        Args:
            obj: The object to encode.

        Returns:
            A JSON-serializable representation of the object.

        Raises:
            TypeError: If the object cannot be encoded.
        """
        if isinstance(obj, datetime):
            return {"__datetime__": obj.isoformat()}
        if isinstance(obj, date):
            return {"__date__": obj.isoformat()}
        if hasattr(obj, "__dict__"):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")
