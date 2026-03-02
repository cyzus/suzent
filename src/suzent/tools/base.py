"""
Lightweight Tool base class for pydantic-ai integration.

Each Tool subclass defines a ``forward()`` method with typed parameters
that pydantic-ai uses directly for JSON schema generation.  The registry
auto-wraps ``forward()`` as a pydantic-ai tool function.
"""


class Tool:
    """Base class for tool implementations.

    Subclasses set class attributes and implement ``forward()``.
    The registry reads ``name``, ``tool_name``, and ``requires_approval``
    to build the pydantic-ai tool list.
    """

    name: str = ""  # Registry key (e.g., "ReadFileTool")
    tool_name: str = ""  # pydantic-ai function name (e.g., "read_file")
    requires_approval: bool = False

    def __init__(self, *args, **kwargs):
        pass

    def forward(self, **kwargs):
        raise NotImplementedError("Subclasses must implement forward()")
