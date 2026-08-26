"""Filesystem tool suite exports.

Re-exports resolve on first attribute access. ``edit_file_tool`` pulls in
pydantic-ai, so eager re-exports made importing a leaf module such as
``path_resolver`` cost the whole agent runtime.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.tools.filesystem.edit_file_tool import EditFileTool as EditFileTool
    from suzent.tools.filesystem.file_tool_utils import (
        detect_text_encoding as detect_text_encoding,
    )
    from suzent.tools.filesystem.file_tool_utils import (
        get_or_create_path_resolver as get_or_create_path_resolver,
    )
    from suzent.tools.filesystem.file_tool_utils import (
        is_binary_content as is_binary_content,
    )
    from suzent.tools.filesystem.file_tool_utils import (
        is_windows_unc_path as is_windows_unc_path,
    )
    from suzent.tools.filesystem.glob_tool import GlobTool as GlobTool
    from suzent.tools.filesystem.grep_tool import GrepTool as GrepTool
    from suzent.tools.filesystem.path_resolver import PathResolver as PathResolver
    from suzent.tools.filesystem.read_file_tool import ReadFileTool as ReadFileTool
    from suzent.tools.filesystem.write_file_tool import WriteFileTool as WriteFileTool

_EXPORTS = {
    "PathResolver": "suzent.tools.filesystem.path_resolver",
    "ReadFileTool": "suzent.tools.filesystem.read_file_tool",
    "WriteFileTool": "suzent.tools.filesystem.write_file_tool",
    "EditFileTool": "suzent.tools.filesystem.edit_file_tool",
    "GlobTool": "suzent.tools.filesystem.glob_tool",
    "GrepTool": "suzent.tools.filesystem.grep_tool",
    "get_or_create_path_resolver": "suzent.tools.filesystem.file_tool_utils",
    "is_windows_unc_path": "suzent.tools.filesystem.file_tool_utils",
    "detect_text_encoding": "suzent.tools.filesystem.file_tool_utils",
    "is_binary_content": "suzent.tools.filesystem.file_tool_utils",
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
