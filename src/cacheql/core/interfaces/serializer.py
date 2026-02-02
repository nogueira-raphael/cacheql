"""Serializer interface."""

from typing import Any, Protocol


class ISerializer(Protocol):
    """Contract for serializing/deserializing cached values.

    Serializers handle the conversion between Python objects
    and bytes for storage in cache backends.
    """

    def serialize(self, value: Any) -> bytes:
        """Serialize value to bytes.

        Args:
            value: The Python object to serialize.

        Returns:
            The serialized value as bytes.

        Raises:
            SerializationError: If the value cannot be serialized.
        """
        ...

    def deserialize(self, data: bytes) -> Any:
        """Deserialize bytes to value.

        Args:
            data: The bytes to deserialize.

        Returns:
            The deserialized Python object.

        Raises:
            SerializationError: If the data cannot be deserialized.
        """
        ...
