"""Tool package exports.

Re-exports resolve on first attribute access. Importing a leaf module such as
:mod:`suzent.tools.names` runs this file first, and eager re-exports made that
pull in the filesystem tools -- and pydantic-ai behind them -- for callers that
only wanted a handful of constants.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.tools.base import Tool as Tool
    from suzent.tools.base import ToolErrorCode as ToolErrorCode
    from suzent.tools.base import ToolResult as ToolResult
    from suzent.tools.filesystem import EditFileTool as EditFileTool
    from suzent.tools.filesystem import GlobTool as GlobTool
    from suzent.tools.filesystem import GrepTool as GrepTool
    from suzent.tools.filesystem import PathResolver as PathResolver
    from suzent.tools.filesystem import ReadFileTool as ReadFileTool
    from suzent.tools.filesystem import WriteFileTool as WriteFileTool

_EXPORTS = {
    "Tool": "suzent.tools.base",
    "ToolResult": "suzent.tools.base",
    "ToolErrorCode": "suzent.tools.base",
    "PathResolver": "suzent.tools.filesystem",
    "ReadFileTool": "suzent.tools.filesystem",
    "WriteFileTool": "suzent.tools.filesystem",
    "EditFileTool": "suzent.tools.filesystem",
    "GlobTool": "suzent.tools.filesystem",
    "GrepTool": "suzent.tools.filesystem",
}

__all__ = list(_EXPORTS)


def __getattr__(name: str) -> Any:
    module = _EXPORTS.get(name)
    if module is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module), name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(__all__)
