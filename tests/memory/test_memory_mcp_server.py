"""The memory MCP server other agents use, and the routes behind it."""

import json
from types import SimpleNamespace

import pytest

from suzent.config import CONFIG
from suzent.memory import mcp_server
from suzent.routes import memory_routes


class _Request:
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class _Manager:
    def __init__(self):
        self.calls = []

    async def apply_memory_update(self, **kwargs):
        self.calls.append(kwargs)
        return {"retracted": [], "written": kwargs["fact"]}


@pytest.fixture
def manager(monkeypatch):
    mgr = _Manager()
    monkeypatch.setattr(memory_routes, "get_memory_manager", lambda: mgr)
    return mgr


@pytest.fixture
def writes(monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_external_write", True)


async def test_remember_is_refused_until_the_user_allows_it(manager, monkeypatch):
    monkeypatch.setattr(CONFIG, "memory_external_write", False)

    response = await memory_routes.remember_from_external_agent(
        _Request({"fact": "User likes tea"})
    )

    assert response.status_code == 403
    assert json.loads(response.body)["reasonCode"] == "external_write_disabled"
    assert manager.calls == []


async def test_remember_tags_the_writing_agent(manager, writes):
    response = await memory_routes.remember_from_external_agent(
        _Request({"fact": " User  likes tea ", "kind": "user", "agent": "Claude Code"})
    )

    assert response.status_code == 200
    assert json.loads(response.body) == {"written": "User likes tea"}
    call = manager.calls[0]
    assert call["via"] == "claude-code"
    assert call["fact"] == "User likes tea"
    assert "retract" not in call


@pytest.mark.parametrize(
    "body",
    [
        {"fact": ""},
        {"fact": "x", "kind": "secret"},
        {"fact": "x", "retract": "User likes coffee"},
    ],
)
async def test_remember_rejects_bad_requests(manager, writes, body):
    response = await memory_routes.remember_from_external_agent(_Request(body))

    assert response.status_code == 400
    assert manager.calls == []


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Claude Code", "claude-code"),
        ("codex-mcp-client", "codex-mcp-client"),
        ("", "agent"),
        ("`x`; rm", "x-rm"),
    ],
)
def test_agent_slug_is_tag_safe(name, slug):
    assert memory_routes.agent_slug(name) == slug


async def test_external_access_toggle_persists(monkeypatch):
    saved = {}
    monkeypatch.setattr(
        "suzent.routes.config_routes._load_local_config_file", lambda: {}
    )
    monkeypatch.setattr(
        "suzent.routes.config_routes._save_local_config_file", saved.update
    )
    monkeypatch.setattr(CONFIG, "memory_external_write", False)

    response = await memory_routes.save_external_access(
        _Request({"write_enabled": True})
    )

    assert json.loads(response.body) == {"write_enabled": True}
    assert saved == {"memory_external_write": True}
    assert CONFIG.memory_external_write is True
    bad = await memory_routes.save_external_access(_Request({"write_enabled": "yes"}))
    assert bad.status_code == 400


def test_hits_read_as_a_numbered_list():
    text = mcp_server.format_hits(
        [
            {
                "content": "User prefers tea",
                "created_at": "2026-11-20T10:00:00+00:00",
                "metadata": {"kind": "user"},
            }
        ]
    )

    assert text == "1. User prefers tea  (user, stored 2026-11-20)"
    assert mcp_server.format_hits([]) == "No relevant memories found."


def test_profile_leaves_out_suzents_persona():
    text = mcp_server.format_profile(
        {"persona": "I am Suzent", "user": "Name: Suzy", "facts": "- likes tea"}
    )

    assert "I am Suzent" not in text
    assert "Name: Suzy" in text and "- likes tea" in text


async def test_the_server_lists_three_tools():
    server = mcp_server.build_server(SimpleNamespace())

    tools = {tool.name for tool in await server.list_tools()}

    assert tools == {"memory_search", "memory_profile", "memory_remember"}


async def test_remember_names_the_client_unless_overridden():
    bridge = mcp_server.MemoryBridge("http://127.0.0.1:1", agent=None)
    sent = {}

    async def post(path, json=None, **kwargs):
        sent.update(path=path, body=json)
        return {"written": json["fact"]}

    bridge._client.post = post
    server = mcp_server.build_server(bridge)
    ctx = SimpleNamespace(
        session=SimpleNamespace(
            client_params=SimpleNamespace(
                clientInfo=SimpleNamespace(name="claude-code")
            )
        )
    )

    tool = server._tool_manager.get_tool("memory_remember")
    result = await tool.fn(fact="User likes tea", ctx=ctx)

    assert result == "Remembered: User likes tea"
    assert sent["path"] == "/memory/remember"
    assert sent["body"]["agent"] == "claude-code"
    await bridge.aclose()


@pytest.mark.parametrize(
    ("argv", "reserved"),
    [
        (["mcp", "serve"], True),
        (["-v", "mcp", "skill", "--dir", "x"], True),
        (["mcp", "list"], False),
        (["mcp"], False),
    ],
)
def test_stdout_stays_clean_for_serve_and_skill(argv, reserved):
    from suzent.cli import _stdout_is_reserved

    ctx = SimpleNamespace(invoked_subcommand="mcp")

    assert _stdout_is_reserved(ctx, argv) is reserved


def test_the_skill_ships_with_the_package():
    text = mcp_server.SKILL_PATH.read_text(encoding="utf-8")

    assert text.startswith("---\nname: suzent-memory\n")
    for tool in ("memory_search", "memory_profile", "memory_remember"):
        assert tool in text
