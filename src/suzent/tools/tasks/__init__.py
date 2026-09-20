"""Task and goal tool exports.

Re-exports resolve on first attribute access, matching
:mod:`suzent.tools.filesystem` -- these modules pull in pydantic-ai, so eager
re-exports would charge that cost to anything importing a single leaf.
"""

import importlib
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from suzent.tools.tasks.goal_tool import GoalTool as GoalTool
    from suzent.tools.tasks.task_create_tool import TaskCreateTool as TaskCreateTool
    from suzent.tools.tasks.task_list_tool import TaskListTool as TaskListTool
    from suzent.tools.tasks.task_update_tool import TaskUpdateTool as TaskUpdateTool

_EXPORTS = {
    "GoalTool": "suzent.tools.tasks.goal_tool",
    "TaskCreateTool": "suzent.tools.tasks.task_create_tool",
    "TaskUpdateTool": "suzent.tools.tasks.task_update_tool",
    "TaskListTool": "suzent.tools.tasks.task_list_tool",
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
