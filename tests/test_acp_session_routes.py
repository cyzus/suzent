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
