"""Unit tests for core utility functions (suzent.utils)."""

from dataclasses import dataclass

from suzent.utils import CustomJsonEncoder, to_serializable


class TestCustomJsonEncoder:
    """Tests for CustomJsonEncoder."""

    def test_encode_dataclass(self):
        """Test encoding a dataclass."""

        @dataclass
        class Person:
            name: str
            age: int

        person = Person("Alice", 30)
        encoder = CustomJsonEncoder()
        result = encoder.default(person)

        assert result == {"name": "Alice", "age": 30}

    def test_encode_exception(self):
        """Test encoding an exception."""
        error = ValueError("test error")
        encoder = CustomJsonEncoder()
        result = encoder.default(error)

        assert result["error_type"] == "ValueError"
        assert result["message"] == "test error"
        assert "args" in result

    def test_to_serializable_simple(self):
        """Test to_serializable with simple types."""
        data = {"string": "hello", "number": 42, "boolean": True, "null": None}

        result = to_serializable(data)

        assert result == data

    def test_to_serializable_nested(self):
        """Test to_serializable with nested structures."""
        data = {"outer": {"inner": {"value": 123}}, "list": [1, 2, 3]}

        result = to_serializable(data)

        assert result == data
