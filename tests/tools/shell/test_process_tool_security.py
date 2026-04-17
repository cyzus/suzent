from types import SimpleNamespace

from suzent.tools.shell.process_tool import ProcessTool


def _ctx(tmp_path, sandbox_enabled=True):
    deps = SimpleNamespace(
        chat_id="chat-1",
        sandbox_enabled=sandbox_enabled,
        workspace_root=str(tmp_path),
        custom_volumes=[],
        auto_approve_tools=False,
        tool_approval_policy={},
    )
    return SimpleNamespace(deps=deps)


def test_respects_explicit_deny_policy(tmp_path):
    ctx = _ctx(tmp_path)
    ctx.deps.tool_approval_policy["process_manage"] = "always_deny"

    result = ProcessTool().forward(
        ctx,
        process_id="abcdef123456",
        action="status",
    )

    assert not result.success
    assert result.error_code.value == "permission_denied"
    assert result.message == "Tool 'process_manage' is denied by policy"


def test_rejects_invalid_process_id(tmp_path):
    tool = ProcessTool()

    result = tool.forward(_ctx(tmp_path), process_id="not-valid", action="poll")

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert result.message == "Invalid process_id format."


def test_rejects_negative_offset(tmp_path):
    tool = ProcessTool()

    result = tool.forward(
        _ctx(tmp_path),
        process_id="abcdef123456",
        action="poll",
        offset=-1,
    )

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert result.message == "offset must be greater than or equal to 0."


def test_rejects_unknown_action(tmp_path):
    tool = ProcessTool()

    result = tool.forward(
        _ctx(tmp_path),
        process_id="abcdef123456",
        action="delete",
    )

    assert not result.success
    assert result.error_code.value == "invalid_argument"
    assert "Unknown action 'delete'" in result.message


def test_host_kill_always_evicts_registry_entry(monkeypatch, tmp_path):
    class _FakeRegistry:
        def __init__(self):
            self.kill_calls = []
            self.evict_calls = []

        def kill(self, chat_id, process_id):
            self.kill_calls.append((chat_id, process_id))
            return False

        def evict(self, chat_id, process_id):
            self.evict_calls.append((chat_id, process_id))

    registry = _FakeRegistry()
    monkeypatch.setattr(
        "suzent.tools.shell.host_process_registry.HostProcessRegistry",
        lambda: registry,
    )

    result = ProcessTool().forward(
        _ctx(tmp_path, sandbox_enabled=False),
        process_id="abcdef123456",
        action="kill",
    )

    assert not result.success
    assert registry.kill_calls == [("chat-1", "abcdef123456")]
    assert registry.evict_calls == [("chat-1", "abcdef123456")]


def test_host_poll_evicts_when_done_and_drained(monkeypatch, tmp_path):
    class _FakeRegistry:
        def __init__(self):
            self.poll_calls = []
            self.evict_calls = []

        def poll(self, chat_id, process_id, offset):
            self.poll_calls.append((chat_id, process_id, offset))
            return {
                "output": "",
                "offset": offset,
                "done": True,
                "exit_code": 0,
            }

        def evict(self, chat_id, process_id):
            self.evict_calls.append((chat_id, process_id))

    registry = _FakeRegistry()
    monkeypatch.setattr(
        "suzent.tools.shell.host_process_registry.HostProcessRegistry",
        lambda: registry,
    )

    result = ProcessTool().forward(
        _ctx(tmp_path, sandbox_enabled=False),
        process_id="abcdef123456",
        action="poll",
        offset=42,
    )

    assert result.success
    assert registry.poll_calls == [("chat-1", "abcdef123456", 42)]
    assert registry.evict_calls == [("chat-1", "abcdef123456")]
