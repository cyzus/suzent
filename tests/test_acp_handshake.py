"""Regression tests for the ACP handshake, resume fallback, and probe route."""

import json
import sys

import pytest

from suzent.acp.manager import ACPManager
from suzent.acp.registry import ACPAgentRegistry

# Behaves like a real ACP agent: refuses session methods before `initialize`,
# and advertises whether it can load a previous session.
STRICT_AGENT = r"""
import json, sys
LOAD = {load}
initialized = False
for line in sys.stdin:
    msg = json.loads(line)
    m = msg.get("method")
    if m == "initialize":
        initialized = True
        print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"result":{{
            "protocolVersion":1,
            "agentCapabilities":{{"loadSession":LOAD}},
            "agentInfo":{{"name":"strict-mock","version":"9"}}}}}}), flush=True)
    elif m in ("session/new", "session/load"):
        if not initialized:
            print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"error":{{
                "code":-32002,"message":"initialize must be called first"}}}}), flush=True)
        elif m == "session/load" and not LOAD:
            print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"error":{{
                "code":-32601,"message":"session/load unsupported"}}}}), flush=True)
        else:
            sid = msg["params"].get("sessionId", "fresh-session")
            print(json.dumps({{"jsonrpc":"2.0","id":msg["id"],"result":{{"sessionId":sid}}}}), flush=True)
"""


# Advertises loadSession but no longer holds the id -- what codex does once its
# rollout file is gone ("no rollout found for thread id ...").
ROTTEN_AGENT = r"""
import json, sys
for line in sys.stdin:
    msg = json.loads(line)
    m = msg.get("method")
    if m == "initialize":
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"result":{
            "protocolVersion":1,
            "agentCapabilities":{"loadSession":True},
            "agentInfo":{"name":"rotten-mock","version":"9"}}}), flush=True)
    elif m == "session/load":
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],"error":{
            "code":-32603,"message":"Internal error",
            "data":{"details":"no rollout found for thread id abc"}}}), flush=True)
    elif m == "session/new":
        print(json.dumps({"jsonrpc":"2.0","id":msg["id"],
            "result":{"sessionId":"fresh-session"}}), flush=True)
"""


def _rotten_manager(tmp_path) -> ACPManager:
    script = tmp_path / "rotten.py"
    script.write_text(ROTTEN_AGENT)
    config = tmp_path / "rotten_agents.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "rotten",
                        "name": "Rotten",
                        "command": [sys.executable, "-u", str(script)],
                    }
                ]
            }
        )
    )
    return ACPManager(ACPAgentRegistry(config))


def _manager(tmp_path, load_session: bool) -> ACPManager:
    script = tmp_path / f"strict_{load_session}.py"
    script.write_text(STRICT_AGENT.format(load="True" if load_session else "False"))
    config = tmp_path / "acp_agents.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {
                        "id": "strict",
                        "name": "Strict",
                        "command": [sys.executable, "-u", str(script)],
                    }
                ]
            }
        )
    )
    return ACPManager(ACPAgentRegistry(config))


@pytest.mark.asyncio
async def test_connect_performs_initialize_before_session_new(tmp_path):
    """A spec-compliant agent rejects session/new unless `initialize` ran first."""
    manager = _manager(tmp_path, load_session=True)
    try:
        managed = await manager.create("chat-1", "strict", str(tmp_path))
        assert managed.session_id == "fresh-session"
        assert managed.protocol_version == 1
        assert managed.capabilities == {"loadSession": True}
        assert managed.agent_info["name"] == "strict-mock"
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_resume_loads_session_when_agent_supports_it(tmp_path):
    manager = _manager(tmp_path, load_session=True)
    try:
        managed = await manager.resume(
            "chat-1", "strict", "prior-session", str(tmp_path)
        )
        assert managed.session_id == "prior-session"
        assert managed.resumed is True
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_resume_survives_a_session_the_agent_no_longer_backs(tmp_path):
    """A failed session/load must not leave the chat unable to send.

    Codex advertises loadSession, then rejects ids whose rollout file is gone.
    That error used to escape as a raw JSON-RPC dict and end the turn.
    """
    manager = _rotten_manager(tmp_path)
    try:
        managed = await manager.resume(
            "chat-1", "rotten", "prior-session", str(tmp_path)
        )
        assert managed.session_id == "fresh-session"
        assert managed.resumed is False
        assert "no rollout found" in managed.load_error
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_resume_falls_back_to_new_session_without_load_capability(tmp_path):
    """Agents that can't load sessions must still get a usable session."""
    manager = _manager(tmp_path, load_session=False)
    try:
        managed = await manager.resume(
            "chat-1", "strict", "prior-session", str(tmp_path)
        )
        assert managed.session_id == "fresh-session"
        assert managed.resumed is False
    finally:
        await manager.shutdown()


@pytest.mark.asyncio
async def test_probe_returns_handshake_data_and_leaves_no_process(
    tmp_path, monkeypatch
):
    import suzent.acp.manager as manager_module
    from suzent.routes.acp_routes import probe_acp_agent

    manager = _manager(tmp_path, load_session=True)
    monkeypatch.setattr(manager_module, "_manager", manager)

    class _Request:
        path_params = {"agent_id": "strict"}

    try:
        response = await probe_acp_agent(_Request())
        assert response.status_code == 200
        body = json.loads(response.body)
        assert body["protocolVersion"] == 1
        assert body["capabilities"] == {"loadSession": True}
        assert body["agentInfo"]["name"] == "strict-mock"
        # The probe subprocess must be torn down, not left running.
        assert manager.list_active() == []
    finally:
        await manager.shutdown()


def _events(chunks):
    out = []
    for chunk in chunks:
        if chunk.startswith("data: ") and not chunk.startswith("data: [DONE]"):
            out.append(json.loads(chunk[6:].strip()))
    return out


async def _collect_turn(prompt_impl):
    """Drive stream_acp_turn against a stubbed manager/database."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "s"}
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "s", "/tmp"
        managed.client.prompt = prompt_impl
        managed.updates = asyncio.Queue()

        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        return _events([chunk async for chunk in stream_acp_turn("chat-1", "hi")])


@pytest.mark.asyncio
async def test_turn_closes_assistant_message_when_agent_errors():
    """A mid-turn failure must still emit TEXT_MESSAGE_END, or the UI streams forever."""

    async def boom(session_id, message):
        raise RuntimeError("agent crashed")

    events = await _collect_turn(boom)
    types = [event["type"] for event in events]
    assert "TEXT_MESSAGE_START" in types
    assert "TEXT_MESSAGE_END" in types
    assert types.index("TEXT_MESSAGE_END") < types.index("RUN_ERROR")
    assert "agent crashed" in events[-1]["message"]


@pytest.mark.asyncio
async def test_turn_closes_assistant_message_when_output_is_empty():
    async def silent(session_id, message):
        return {"text": ""}

    events = await _collect_turn(silent)
    types = [event["type"] for event in events]
    assert types.index("TEXT_MESSAGE_END") < types.index("RUN_ERROR")


def test_user_override_keeps_builtin_install_metadata(tmp_path):
    """Repointing a built-in's command must not strip its setup commands."""
    config = tmp_path / "acp_agents.json"
    config.write_text(
        json.dumps(
            {
                "agents": [
                    {"id": "claude-code", "command": ["/opt/my/acp-adapter"]},
                    {"id": "custom", "command": ["whatever"]},
                ]
            }
        )
    )
    agents = {a.id: a for a in ACPAgentRegistry(config).list_agents()}

    overridden = agents["claude-code"]
    assert overridden.command == ["/opt/my/acp-adapter"]
    assert overridden.login_command == ["claude", "auth", "login"]
    assert overridden.name == "Claude Code (CLI)"
    assert overridden.builtin is True

    # A genuinely new agent has no metadata to inherit.
    assert agents["custom"].install_command is None
    assert agents["custom"].builtin is False


@pytest.mark.asyncio
async def test_turn_announces_when_resume_lost_the_session():
    """A silent fresh session looks like amnesia; the stream must say so."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "old-1"}
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "new-2", "/tmp"
        managed.resumed = False
        managed.load_error = ""
        managed.updates = asyncio.Queue()

        async def prompt(session_id, message):
            return {"text": "hi"}

        managed.client.prompt = prompt
        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        events = _events([c async for c in stream_acp_turn("chat-1", "hi")])

    resets = [e for e in events if e.get("name") == "acp.session_reset"]
    assert len(resets) == 1
    assert resets[0]["value"]["requestedSessionId"] == "old-1"
    assert resets[0]["value"]["sessionId"] == "new-2"
    assert resets[0]["value"]["reason"] == "load_session_unsupported"


@pytest.mark.asyncio
async def test_turn_reports_why_the_agent_refused_the_session():
    """A rejected session/load is a different story from an unsupported one."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "old-1"}
        chat.messages = []
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "new-2", "/tmp"
        managed.resumed = False
        managed.load_error = "no rollout found for thread id abc"
        managed.updates = asyncio.Queue()

        async def prompt(session_id, message):
            return {"text": "hi"}

        managed.client.prompt = prompt
        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        events = _events([c async for c in stream_acp_turn("chat-1", "hi")])

    reset = next(e for e in events if e.get("name") == "acp.session_reset")
    assert reset["value"]["reason"] == "load_session_failed"
    assert "no rollout found" in reset["value"]["detail"]
    # The turn still ran rather than dying on the load error.
    assert any(e.get("type") == "AGENT_FINISHED" for e in events)


@pytest.mark.asyncio
async def test_file_mentions_do_not_duplicate_the_user_message():
    """/chat/send already stored the row; the annotated prompt must not re-add it."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "s"}
        chat.messages = [{"role": "user", "content": "review this"}]
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "s", "/tmp"
        managed.resumed = True
        managed.load_error = ""
        managed.updates = asyncio.Queue()

        prompts: list[str] = []

        async def prompt(session_id, message):
            prompts.append(message)
            return {"text": "ok"}

        managed.client.prompt = prompt
        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        [
            c
            async for c in stream_acp_turn(
                "chat-1",
                "review this",
                file_mentions=[{"path": "/repo/main.py", "type": "file"}],
            )
        ]

    user_writes = [
        call.args[1]
        for call in db.append_chat_message.call_args_list
        if call.args[1].get("role") == "user"
    ]
    assert user_writes == [], "the user's message was stored a second time"
    # The agent still receives the annotated prompt.
    assert "/repo/main.py" in prompts[0]
    assert prompts[0].endswith("review this")


@pytest.mark.asyncio
async def test_first_acp_turn_renames_the_chat():
    """ACP turns skip suzent.streaming, so they had to ask for a title here."""
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
        patch(
            "suzent.acp.runtime.generate_auto_title",
            AsyncMock(return_value="Reviewing The Parser"),
        ) as mock_title,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "s"}
        chat.messages = []
        chat.title = "New Chat"
        chat.turn_count = 0
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "s", "/tmp"
        managed.resumed = True
        managed.restored = False
        managed.load_error = ""
        managed.updates = asyncio.Queue()

        async def prompt(session_id, message):
            return {"text": "ok"}

        managed.client.prompt = prompt
        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        events = _events(
            [c async for c in stream_acp_turn("chat-1", "review the parser")]
        )

    assert mock_title.await_args.args == ("chat-1", "review the parser")
    renamed = next(e for e in events if e.get("name") == "chat_title_updated")
    assert renamed["value"] == {"chat_id": "chat-1", "title": "Reviewing The Parser"}


@pytest.mark.asyncio
async def test_a_named_chat_is_not_retitled_by_a_later_acp_turn():
    import asyncio
    from unittest.mock import AsyncMock, MagicMock, patch

    from suzent.acp.runtime import stream_acp_turn

    with (
        patch("suzent.acp.runtime.get_database") as mock_get_db,
        patch("suzent.acp.runtime.get_acp_manager") as mock_get_manager,
        patch("suzent.acp.runtime.generate_auto_title", AsyncMock()) as mock_title,
    ):
        chat = MagicMock()
        chat.config = {"runtime": "acp", "acp_agent_id": "a", "acp_session_id": "s"}
        chat.messages = []
        chat.title = "Parser Rewrite"
        chat.turn_count = 4
        db = MagicMock()
        db.get_chat.return_value = chat
        mock_get_db.return_value = db

        managed = MagicMock()
        managed.agent_id, managed.session_id, managed.cwd = "a", "s", "/tmp"
        managed.resumed = True
        managed.restored = False
        managed.load_error = ""
        managed.updates = asyncio.Queue()

        async def prompt(session_id, message):
            return {"text": "ok"}

        managed.client.prompt = prompt
        manager = AsyncMock()
        manager.ensure.return_value = managed
        mock_get_manager.return_value = manager

        events = _events([c async for c in stream_acp_turn("chat-1", "and now this")])

    mock_title.assert_not_awaited()
    assert not any(e.get("name") == "chat_title_updated" for e in events)
