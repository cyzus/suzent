from types import SimpleNamespace

import pytest

from suzent.tools.base import Tool
from suzent.tools.capability import is_denied
from suzent.tools.names import migrate_shell_tool_names


def test_saved_image_vision_selection_uses_visual_analysis_tool() -> None:
    assert migrate_shell_tool_names(["ImageVisionTool", "ReadFileTool"]) == [
        "VisualAnalysisTool",
        "ReadFileTool",
    ]


@pytest.mark.parametrize("legacy_name", ["analyze_image", "ImageVisionTool"])
def test_legacy_visual_denial_still_blocks_new_tool(legacy_name: str) -> None:
    policy = {legacy_name: "always_deny"}
    deps = SimpleNamespace(tool_approval_policy=policy)
    assert Tool.is_tool_denied(deps, "analyze_visual") is not None
    assert is_denied("analyze_visual", frozenset(), policy)
    assert is_denied("analyze_visual", frozenset({legacy_name}), {})
