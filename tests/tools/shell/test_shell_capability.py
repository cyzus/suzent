from types import SimpleNamespace

from suzent.tools.base import truncate_tool_output
from suzent.tools.registry import expand_tool_dependencies, get_tool_groups
from suzent.tools.shell import cleanup_shell_session
from suzent.tools.shell.shell_tools import RunCommandTool
from suzent.tools.shell.capability import ShellCapability
from suzent.tools.shell.host_process_registry import HostProcessRegistry


def test_legacy_shell_tools_migrate_to_capability() -> None:
    assert expand_tool_dependencies(["ReadFileTool", "BashTool"]) == [
        "ReadFileTool",
        "ShellTool",
        "StartCommandTool",
        "CheckCommandTool",
        "StopCommandTool",
    ]


def test_shell_dependency_expansion_is_stable() -> None:
    selected = ["BashTool", "ProcessTool", "BashTool"]
    assert expand_tool_dependencies(selected) == [
        "ShellTool",
        "StartCommandTool",
        "CheckCommandTool",
        "StopCommandTool",
    ]


def test_process_tool_is_not_a_separate_ui_toggle() -> None:
    execution = next(
        group for group in get_tool_groups() if group["label"] == "Execution"
    )
    assert "ShellTool" in execution["tools"]
    assert "ProcessTool" not in execution["tools"]


def test_shell_capability_contributes_both_runtime_tools() -> None:
    toolset = ShellCapability().get_toolset()
    assert set(toolset.tools) == {
        "run_command",
        "start_command",
        "check_command",
        "stop_command",
    }


def test_shell_output_truncation_keeps_error_tail() -> None:
    text = "old output\n" * 20 + "fatal error"
    truncated = truncate_tool_output(text, 40, keep_tail=True)
    assert truncated.startswith("... [")
    assert truncated.endswith("fatal error")


def test_host_env_can_strip_inherited_secrets(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "secret")
    monkeypatch.setenv("SAFE_VALUE", "visible")
    monkeypatch.setattr("suzent.config.CONFIG.shell_denied_env_patterns", ["OPENAI_*"])
    monkeypatch.setattr("suzent.config.CONFIG.shell_env", None)
    monkeypatch.setattr(
        "suzent.tools.shell.bash_tool.get_database",
        SimpleNamespace,
        raising=False,
    )

    tool = RunCommandTool()
    tool.workspace_root = str(tmp_path)
    env = tool._get_host_env()

    assert "OPENAI_API_KEY" not in env
    assert env["SAFE_VALUE"] == "visible"


def test_wrong_chat_cannot_evict_host_process_entry(tmp_path) -> None:
    registry = HostProcessRegistry()
    process_id = "abcdef123456"
    output_file = tmp_path / "output.log"
    output_file.write_text("output", encoding="utf-8")
    entry = SimpleNamespace(chat_id="owner", output_file=output_file)
    registry._processes[process_id] = entry

    try:
        registry.evict("other-chat", process_id)
        assert registry._processes[process_id] is entry
        assert output_file.exists()
    finally:
        registry._processes.pop(process_id, None)


def test_shell_session_cleanup_covers_host_and_sandbox(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    class _Registry:
        def evict_chat(self, chat_id: str) -> None:
            calls.append(("host", chat_id))

    class _SandboxManager:
        @classmethod
        def remove_session_from_all_managers(cls, chat_id: str) -> None:
            calls.append(("sandbox", chat_id))

    monkeypatch.setattr(
        "suzent.tools.shell.host_process_registry.HostProcessRegistry", _Registry
    )
    monkeypatch.setattr("suzent.sandbox.SandboxManager", _SandboxManager)

    cleanup_shell_session("chat-1")

    assert calls == [("host", "chat-1"), ("sandbox", "chat-1")]
