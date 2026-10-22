"""SUZENT's own tools: equipped only for the Focal Agent, and refused elsewhere.

Each has an empty ``group`` and is not deferrable, so no other chat can equip
or discover it. Which of them SUZENT gets is ``FOCAL_TOOL_NAMES`` in
:mod:`suzent.core.focal_agent`. Dispatch and wake-ups subclass ``AgentSendTool``
and ``ScheduleTool`` and call their internals (``_deliver``, ``_create`` and
the like), so check here when those change.

Re-exports resolve on first attribute access, matching :mod:`suzent.tools.agents`.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.tools.focal.dispatch import FocalDispatchTool as FocalDispatchTool
    from suzent.tools.focal.notes import FocalNotesTool as FocalNotesTool
    from suzent.tools.focal.schedule import FocalScheduleTool as FocalScheduleTool

_EXPORTS = {
    "FocalDispatchTool": "suzent.tools.focal.dispatch",
    "FocalNotesTool": "suzent.tools.focal.notes",
    "FocalScheduleTool": "suzent.tools.focal.schedule",
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
