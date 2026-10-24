from suzent.tools.names import migrate_shell_tool_names


def test_saved_image_vision_selection_uses_visual_analysis_tool() -> None:
    assert migrate_shell_tool_names(["ImageVisionTool", "ReadFileTool"]) == [
        "VisualAnalysisTool",
        "ReadFileTool",
    ]
