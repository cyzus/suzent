from suzent.tools.capability import RegisteredToolCapability
from suzent.tools.registry import (
    get_tool_capabilities,
    group_tools_by_capability,
    list_configurable_tools,
)


def test_capability_catalog_covers_every_configurable_tool_once() -> None:
    catalog = get_tool_capabilities()
    catalog_tools = [tool for capability in catalog for tool in capability["tools"]]
    catalog_ids = [tool["id"] for tool in catalog_tools]

    assert sorted(catalog_ids) == list_configurable_tools()
    assert len(catalog_ids) == len(set(catalog_ids))
    assert all(capability["description"] for capability in catalog)
    assert all(tool["name"] and tool["description"] for tool in catalog_tools)
    assert all("Base class" not in tool["description"] for tool in catalog_tools)


def test_selected_tools_are_grouped_by_capability() -> None:
    grouped = group_tools_by_capability(
        ["ReadFileTool", "RunCommandTool", "CheckCommandTool", "WebSearchTool"]
    )

    assert grouped == {
        "filesystem": ["ReadFileTool"],
        "shell": ["RunCommandTool", "CheckCommandTool"],
        "web": ["WebSearchTool"],
    }


def test_tasks_and_goals_are_separate_from_orchestration_tools() -> None:
    grouped = group_tools_by_capability(
        ["GoalTool", "TaskCreateTool", "AgentTool", "AgentListTool"]
    )

    assert grouped == {
        "tasks-goals": ["GoalTool", "TaskCreateTool"],
        "orchestration": ["AgentTool", "AgentListTool"],
    }


def test_asking_the_user_is_separate_from_delegating() -> None:
    """Interaction and Orchestration were one "Agent" group, which put talking
    to the user and spawning sub-agents behind the same header."""
    grouped = group_tools_by_capability(
        ["AskQuestionTool", "RenderUITool", "SkillTool"]
    )

    assert grouped == {
        "interaction": ["AskQuestionTool", "RenderUITool"],
        "orchestration": ["SkillTool"],
    }


def test_registered_capability_exposes_only_selected_tools() -> None:
    capability = RegisteredToolCapability("filesystem", ("ReadFileTool", "GlobTool"))

    assert set(capability.get_toolset().tools) == {"read_file", "glob_search"}


def test_catalog_reports_whether_unchecking_denies_a_tool() -> None:
    """An unchecked deferrable tool stays in the ToolSearch pool, so the picker
    needs the flag to avoid telling the user it is off when it is not."""
    tools = {
        tool["id"]: tool
        for capability in get_tool_capabilities()
        for tool in capability["tools"]
    }

    assert all("deferrable" in tool for tool in tools.values())
    # Shell tools opt out of the pool: unchecking one really does deny it.
    assert tools["RunCommandTool"]["deferrable"] is False
    assert tools["WebSearchTool"]["deferrable"] is True
