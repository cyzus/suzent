"""Route tests for /acp/sessions: chat binding on create, scoping on list."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from suzent.routes import acp_routes


class _Request:
    """Minimal stand-in for a Starlette request body."""

    def __init__(self, payload: dict):
        self._payload = payload

    async def json(self) -> dict:
        return self._payload


class _ListRequest:
    """Minimal stand-in for a Starlette request with a query string."""

    def __init__(self, **params: str):
        self.query_params = params


def _managed(session_id: str = "sess-1"):
    managed = MagicMock()
    managed.session_id = session_id
    return managed


def _manager(session_id: str = "sess-1"):
    manager = MagicMock()
    manager.create = AsyncMock(return_value=_managed(session_id))
    return manager


def _body(response) -> dict:
    return json.loads(response.body)


@pytest.mark.asyncio
async def test_attaches_to_the_existing_chat_instead_of_creating_one(temp_db):
    """The chat picker already made a chat before the first send.

    Creating another one here is what put every ACP conversation in the
    sidebar twice — once as "New Chat" and once as "ACP Session".
    """
    chat_id = temp_db.create_chat("New Chat", {})
    before = len(temp_db.list_chats())

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=_manager()),
    ):
        response = await acp_routes.create_acp_session(
            _Request({"agent_id": "claude-code", "chat_id": chat_id})
        )

    assert response.status_code == 201
    assert _body(response)["chat_id"] == chat_id
    assert len(temp_db.list_chats()) == before, "a second chat was created"

    config = temp_db.get_chat(chat_id).config
    assert config["runtime"] == "acp"
    assert config["acp_agent_id"] == "claude-code"
    assert config["acp_session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_still_creates_a_chat_when_the_caller_names_none(temp_db):
    before = len(temp_db.list_chats())

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=_manager("sess-2")),
    ):
        response = await acp_routes.create_acp_session(
            _Request({"agent_id": "claude-code"})
        )

    assert response.status_code == 201
    assert len(temp_db.list_chats()) == before + 1
    assert (
        temp_db.get_chat(_body(response)["chat_id"]).config["acp_session_id"]
        == "sess-2"
    )


@pytest.mark.asyncio
async def test_unknown_chat_id_is_rejected(temp_db):
    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=_manager()),
    ):
        response = await acp_routes.create_acp_session(
            _Request({"agent_id": "claude-code", "chat_id": "ghost"})
        )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_a_failed_handshake_does_not_delete_the_caller_s_chat(temp_db):
    """Only a chat this route created may be rolled back."""
    chat_id = temp_db.create_chat("New Chat", {})
    manager = MagicMock()
    manager.create = AsyncMock(side_effect=RuntimeError("agent not available"))

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=manager),
    ):
        response = await acp_routes.create_acp_session(
            _Request({"agent_id": "claude-code", "chat_id": chat_id})
        )

    assert response.status_code == 500
    assert temp_db.get_chat(chat_id) is not None, "the user's chat was deleted"


@pytest.mark.asyncio
async def test_a_failed_handshake_rolls_back_a_chat_this_route_created(temp_db):
    before = len(temp_db.list_chats())
    manager = MagicMock()
    manager.create = AsyncMock(side_effect=RuntimeError("agent not available"))

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=manager),
    ):
        response = await acp_routes.create_acp_session(
            _Request({"agent_id": "claude-code"})
        )

    assert response.status_code == 500
    assert len(temp_db.list_chats()) == before


@pytest.mark.asyncio
async def test_a_failed_handshake_leaves_the_caller_s_chat_on_its_own_runtime(temp_db):
    """A native chat must not be stranded on an agent that never answered.

    The route writes ``runtime: acp`` before the handshake, so without a
    rollback a single failed connect made the chat unusable for good.
    """
    chat_id = temp_db.create_chat("New Chat", {"model": "claude-opus-5"})
    manager = MagicMock()
    manager.create = AsyncMock(side_effect=RuntimeError("agent not available"))

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=manager),
    ):
        response = await acp_routes.create_acp_session(
            _Request({"agent_id": "claude-code", "chat_id": chat_id})
        )

    assert response.status_code == 500
    config = temp_db.get_chat(chat_id).config
    assert config.get("runtime") != "acp"
    assert "acp_agent_id" not in config
    assert config.get("model") == "claude-opus-5", "unrelated config was dropped"


def _acp_chats(db) -> None:
    db.create_chat("Codex chat", {"runtime": "acp", "acp_agent_id": "codex"})
    db.create_chat("Codex chat 2", {"runtime": "acp", "acp_agent_id": "codex"})
    db.create_chat("Hermes chat", {"runtime": "acp", "acp_agent_id": "hermes"})


@pytest.mark.asyncio
async def test_sessions_are_scoped_to_the_agent_that_asked(temp_db):
    """Without this, every agent card in settings showed the same total."""
    _acp_chats(temp_db)
    manager = MagicMock()
    manager.list_active.return_value = [
        {"chat_id": "a", "agent_id": "codex"},
        {"chat_id": "b", "agent_id": "hermes"},
    ]

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=manager),
    ):
        response = await acp_routes.list_acp_sessions(_ListRequest(agent_id="codex"))

    body = _body(response)
    assert [s["agent_id"] for s in body["sessions"]] == ["codex", "codex"]
    assert [a["agent_id"] for a in body["active"]] == ["codex"]


@pytest.mark.asyncio
async def test_sessions_without_an_agent_id_still_list_everything(temp_db):
    _acp_chats(temp_db)
    manager = MagicMock()
    manager.list_active.return_value = [{"chat_id": "a", "agent_id": "codex"}]

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=manager),
    ):
        response = await acp_routes.list_acp_sessions(_ListRequest())

    body = _body(response)
    assert len(body["sessions"]) == 3
    assert len(body["active"]) == 1


def test_discover_local_agent_sessions_scans_claude_and_codex(tmp_path):
    from suzent.acp.dialects import discover_local_agent_sessions

    # 1. Claude Code session in ~/.claude/projects/d--workspace-suzent
    claude_dir = tmp_path / ".claude" / "projects" / "d--workspace-suzent"
    claude_dir.mkdir(parents=True)
    claude_file = claude_dir / "sess-claude-1.jsonl"
    claude_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "user",
                        "cwd": "D:\\workspace\\suzent",
                        "timestamp": "2026-11-27T12:00:00Z",
                        "message": {
                            "role": "user",
                            "content": "Fix ACP streaming and session discovery",
                        },
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    found_claude = discover_local_agent_sessions(
        "claude-code", "D:\\workspace\\suzent", home=tmp_path
    )
    assert len(found_claude) == 1
    assert found_claude[0]["session_id"] == "sess-claude-1"
    assert "Fix ACP streaming" in found_claude[0]["title"]

    # 2. Codex session in ~/.codex/sessions/2026/11/27/rollout-*.jsonl
    codex_dir = tmp_path / ".codex" / "sessions" / "2026" / "11" / "27"
    codex_dir.mkdir(parents=True)
    codex_file = codex_dir / "rollout-2026-11-27-sess-codex-1.jsonl"
    codex_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "type": "session_meta",
                        "timestamp": "2026-11-27T13:00:00Z",
                        "payload": {
                            "id": "sess-codex-1",
                            "cwd": "D:\\workspace\\suzent",
                            "thread_source": "user",
                        },
                    }
                ),
                json.dumps(
                    {
                        "type": "response_item",
                        "timestamp": "2026-11-27T13:00:01Z",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": "Audit sidebar consistency across desktop and mobile",
                                }
                            ],
                        },
                    }
                ),
            ]
        ),
        encoding="utf-8",
    )

    found_codex = discover_local_agent_sessions(
        "codex", "D:\\workspace\\suzent", home=tmp_path
    )
    assert len(found_codex) == 1
    assert found_codex[0]["session_id"] == "sess-codex-1"
    assert "Audit sidebar consistency" in found_codex[0]["title"]

    # 3. Cross-agent search without agent_id or cwd filters by query
    searched = discover_local_agent_sessions(None, None, query="sidebar", home=tmp_path)
    assert [s["session_id"] for s in searched] == ["sess-codex-1"]

    # 4. Codex session_index.jsonl thread_name overrides raw first user prompt
    (tmp_path / ".codex" / "session_index.jsonl").write_text(
        json.dumps(
            {
                "id": "sess-codex-1",
                "thread_name": "侧边栏三端一致性审计",
                "updated_at": "2026-11-27T13:05:00Z",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    found_codex_titled = discover_local_agent_sessions(
        "codex", "D:\\workspace\\suzent", home=tmp_path
    )
    assert found_codex_titled[0]["title"] == "侧边栏三端一致性审计"


@pytest.mark.asyncio
async def test_adopt_acp_session_replays_history_via_session_load(temp_db):
    import asyncio

    queue: asyncio.Queue = asyncio.Queue()
    for update in [
        {
            "sessionId": "ext-123",
            "update": {
                "sessionUpdate": "user_message_chunk",
                "content": {"type": "text", "text": "Inspect pyproject.toml"},
            },
        },
        {
            "sessionId": "ext-123",
            "update": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "Reading pyproject.toml..."},
            },
        },
        {
            "sessionId": "ext-123",
            "update": {
                "sessionUpdate": "tool_call",
                "toolCallId": "tc-read-1",
                "kind": "read",
                "rawInput": {"file_path": "pyproject.toml"},
                "rawOutput": "[project]\nname = 'suzent'",
                "status": "completed",
            },
        },
        {
            "sessionId": "ext-123",
            "update": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "The project name is suzent."},
            },
        },
        {
            "sessionId": "ext-123",
            "update": {
                "sessionUpdate": "session_info_update",
                "title": "ACP Replayed Session Title",
                "updatedAt": "2026-11-28T10:00:00Z",
            },
        },
    ]:
        queue.put_nowait(update)

    managed = MagicMock()
    managed.session_id = "ext-123"
    managed.agent_id = "claude-code"
    managed.resumed = True
    managed.updates = queue

    manager = MagicMock()
    manager.resume = AsyncMock(return_value=managed)

    with (
        patch.object(acp_routes, "get_database", return_value=temp_db),
        patch.object(acp_routes, "get_acp_manager", return_value=manager),
    ):
        response = await acp_routes.adopt_acp_session(
            _Request(
                {
                    "agent_id": "claude-code",
                    "session_id": "ext-123",
                    "cwd": "D:\\workspace\\suzent",
                }
            )
        )

    assert response.status_code == 201, _body(response)
    body = _body(response)
    assert body["session_id"] == "ext-123"
    assert body["imported_messages"] == 2
    assert body["title"] == "ACP Replayed Session Title"

    chat = temp_db.get_chat(body["chat_id"])
    assert chat is not None
    assert chat.title == "ACP Replayed Session Title"
    assert len(chat.messages) == 2
    assert chat.messages[0]["role"] == "user"
    assert chat.messages[0]["content"] == "Inspect pyproject.toml"
    assert chat.messages[1]["role"] == "assistant"
    assert chat.messages[1]["content"] == "The project name is suzent."
    parts = chat.messages[1]["parts"]
    assert [p["type"] for p in parts] == ["reasoning", "tool", "text"]
    assert parts[1]["toolName"] == "read_file"


def test_fork_chat_from_acp_to_native_synthesizes_agent_state(temp_db):
    from suzent.core.agent_serializer import deserialize_state
    from suzent.core.fork import fork_chat

    source_id = temp_db.create_chat(
        title="Claude Code Session",
        config={
            "runtime": "acp",
            "acp_agent_id": "claude-code",
            "acp_agent_name": "Claude Code",
            "acp_session_id": "ext-999",
            "acp_cwd": "D:\\workspace\\suzent",
        },
        messages=[
            {"role": "user", "content": "What is in pyproject.toml?"},
            {
                "role": "assistant",
                "content": "The project name is suzent.",
                "parts": [
                    {
                        "type": "tool",
                        "toolCallId": "tc-1",
                        "toolName": "read_file",
                        "args": "pyproject.toml",
                        "output": "[project]\nname = 'suzent'",
                        "state": "completed",
                    },
                    {"type": "text", "text": "The project name is suzent."},
                ],
            },
        ],
    )

    with patch("suzent.database.get_database", return_value=temp_db):
        new_chat_id, _ = fork_chat(
            source_id,
            target_runtime="native",
            target_model="gemini/gemini-4-argon",
        )

    # Original ACP chat remains untouched
    source_chat = temp_db.get_chat(source_id)
    assert source_chat.config["runtime"] == "acp"
    assert source_chat.config["acp_session_id"] == "ext-999"

    # Forked chat is native, bound to target_model, with synthesized agent_state
    forked_chat = temp_db.get_chat(new_chat_id)
    assert forked_chat is not None
    assert forked_chat.config["runtime"] == "native"
    assert forked_chat.config["model"] == "gemini/gemini-4-argon"
    assert "acp_session_id" not in forked_chat.config
    assert "acp_agent_id" not in forked_chat.config
    assert forked_chat.config["forked_from_chat_id"] == source_id
    assert len(forked_chat.messages) == 2
    assert forked_chat.agent_state is not None
    state = deserialize_state(forked_chat.agent_state)
    assert state is not None
    assert len(state["message_history"]) == 2
