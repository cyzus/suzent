"""
Lightweight Tool base class replacing smolagents.tools.Tool.

This provides just enough interface for the existing tool classes to
continue working when instantiated by the tool functions in tool_functions.py.
pydantic-ai does not use this class directly — it uses the function wrappers.
"""


class Tool:
    """Minimal base class for tool implementations.

    Provides the same interface that existing tool classes expect from
    smolagents.tools.Tool: class attributes (name, description, inputs,
    output_type) and a forward() method.
    """

    name: str = ""
    description: str = ""
    inputs: dict = {}
    output_type: str = "string"
    is_initialized: bool = False

    def __init__(self, *args, **kwargs):
        pass

    def forward(self, **kwargs):
        raise NotImplementedError("Subclasses must implement forward()")
