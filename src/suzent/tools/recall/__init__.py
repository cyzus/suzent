"""Memory and session-recall tool exports.

Named ``recall`` rather than ``memory`` so it does not read as a second
:mod:`suzent.memory` -- this package holds the tools that search that store,
not the store itself.

Re-exports resolve on first attribute access, matching
:mod:`suzent.tools.filesystem`.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.tools.recall.memory_tools import MemorySearchTool as MemorySearchTool
    from suzent.tools.recall.session_search_tool import (
        SessionSearchTool as SessionSearchTool,
    )

_EXPORTS = {
    "MemorySearchTool": "suzent.tools.recall.memory_tools",
    "SessionSearchTool": "suzent.tools.recall.session_search_tool",
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
