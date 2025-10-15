"""
Utility functions and classes for the Suzent server.

This module provides common utilities such as JSON serialization helpers
and other shared functionality.
"""

import json
import types
from dataclasses import asdict, is_dataclass
from json import JSONEncoder
from typing import Any


class CustomJsonEncoder(JSONEncoder):
    """
    Custom JSON encoder to handle serialization of various object types,
    including dataclasses and exceptions.
    """

    def default(self, o: Any) -> Any:
        """
        Convert non-serializable objects to serializable format.
        
        Args:
            o: Object to serialize.
        
        Returns:
            Serializable representation of the object.
        """
        if is_dataclass(o):
            return asdict(o)
        if isinstance(o, Exception):
            return str(o)
        if hasattr(o, "dict"):
            return o.dict()
        if hasattr(o, "__dict__"):
            return {
                k: v
                for k, v in o.__dict__.items()
                if not k.startswith("_") and self._is_json_serializable(v)
            }
        if isinstance(o, types.GeneratorType):
            return list(o)
        return super().default(o)

    def _is_json_serializable(self, value: Any) -> bool:
        """Check if a value is JSON serializable."""
        try:
            json.dumps(value)
            return True
        except (TypeError, OverflowError):
            return False


def to_serializable(obj: Any) -> Any:
    """
    Recursively converts an object to a JSON-serializable format.
    
    Args:
        obj: Object to convert.
    
    Returns:
        JSON-serializable representation of the object.
    """
    return json.loads(json.dumps(obj, cls=CustomJsonEncoder))
