"""Plugin integrations: hosted services the agent reaches once the user signs in."""

import json
import os
from pathlib import Path

import pytest

from suzent.core import secrets as secrets_module
from suzent.core.secrets import SecretManager
from suzent.plugins import PluginManager, integrations

BUILTIN_DIR = Path(__file__).resolve().parents[2] / "plugins"


class _DictBackend:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value

    def delete(self, key):
        self.values.pop(key, None)

    def list_keys(self):
        return list(self.values)


@pytest.fixture
def secrets(monkeypatch):
    backend = _DictBackend()
    manager = SecretManager(backend)
    monkeypatch.setattr(secrets_module, "_instance", manager)
    return backend


@pytest.fixture
def plugins(tmp_path, monkeypatch):
    state = tmp_path / "plugins.json"
    enabled = {pid: {"enabled": True} for pid in ("notion", "linear", "github")}
    state.write_text(json.dumps({"version": 1, "plugins": enabled}))
    manager = PluginManager(
        [], state, builtin_dirs=[BUILTIN_DIR], entry_point_group=None
    )
    import suzent.plugins.manager as manager_module

    monkeypatch.setattr(manager_module, "_manager", manager, raising=False)
    monkeypatch.setattr("suzent.plugins.get_plugin_manager", lambda: manager)
    monkeypatch.setattr(manager_module, "get_plugin_manager", lambda: manager)
    return manager


def _record(manager, plugin_id):
    return next(r for r in manager.records() if r.id == plugin_id)


def test_builtin_plugins_declare_their_service(plugins):
    for plugin_id, auth in (
        ("notion", "oauth"),
        ("linear", "oauth"),
        ("github", "token"),
    ):
        record = _record(plugins, plugin_id)
        assert record.status == "loaded", record.error
        [integration] = record.integrations
        assert integration.auth == auth
        assert integration.url.startswith("https://")


def test_no_toolset_until_signed_in(plugins, secrets):
    assert integrations.connected_toolsets() == []


def test_a_pasted_token_connects_and_stays_out_of_the_environment(
    plugins, secrets, monkeypatch
):
    github = _record(plugins, "github").integrations[0]
    key = integrations.token_key("github", github)
    secrets.values[key] = "github_pat_example"
    monkeypatch.delenv(key, raising=False)

    [toolset] = integrations.connected_toolsets()
    assert integrations.describe("github", github)["connected"] is True
    # Startup copies stored secrets into the environment, which commands the
    # agent runs inherit; integration tokens must not go with them.
    SecretManager(secrets).inject_all_to_env()
    assert key not in os.environ
    assert "github_pat_example" not in os.environ.values()
    assert toolset is not None


def test_signed_in_oauth_service_builds_a_refreshing_client(plugins, secrets):
    from fastmcp import Client

    notion = _record(plugins, "notion").integrations[0]
    namespace = integrations.namespace("notion", notion)
    secrets.values[
        f"SUZENT_MCP_OAUTH::{namespace}::mcp-oauth-token::{notion.url}/tokens"
    ] = "{}"
    seen = {}
    original = notion.build

    def spy(client):
        seen["client"] = client
        return original(client)

    object.__setattr__(notion, "build", spy)
    try:
        [toolset] = integrations.connected_toolsets()
    finally:
        object.__setattr__(notion, "build", original)
    assert isinstance(seen["client"], Client)
    assert toolset is not None


def test_a_broken_integration_does_not_stop_the_agent(plugins, secrets):
    github = _record(plugins, "github").integrations[0]
    secrets.values[integrations.token_key("github", github)] = "token"

    def boom(_):
        raise RuntimeError("server gone")

    original = github.build
    object.__setattr__(github, "build", boom)
    try:
        assert integrations.connected_toolsets() == []
    finally:
        object.__setattr__(github, "build", original)


def test_register_integration_rejects_plain_http(tmp_path):
    from suzent.plugins.context import PluginContext
    from suzent.plugins.manifest import PluginManifest

    ctx = PluginContext(PluginManifest(id="x", version="1"), tmp_path)
    with pytest.raises(ValueError):
        ctx.register_integration(
            integrations.Integration(
                id="x", name="X", url="http://example.com", auth="token", build=str
            )
        )


async def test_integration_writes_go_through_approvals(monkeypatch):
    """Integration toolsets get the same approval wrapping as MCP servers."""
    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel
    from pydantic_ai.tools import DeferredToolRequests, ToolDefinition
    from pydantic_ai.toolsets import FunctionToolset

    from suzent import agent_manager

    calls = []
    toolset = FunctionToolset()

    @toolset.tool_plain
    def create_page(title: str) -> str:
        calls.append(title)
        return "created"

    def mark_writing(ctx, defs: list[ToolDefinition]) -> list[ToolDefinition]:
        return [
            d.__class__(**{**d.__dict__, "metadata": {"annotations": {}}}) for d in defs
        ]

    wrapped = agent_manager._as_mcp_toolset(toolset.prepared(mark_writing))
    agent = Agent(
        TestModel(), toolsets=[wrapped], output_type=[str, DeferredToolRequests]
    )
    result = await agent.run("make a page")
    assert isinstance(result.output, DeferredToolRequests)
    assert calls == []


def test_token_connect_and_disconnect_routes(plugins, secrets, monkeypatch):
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from suzent import agent_manager
    from suzent.routes import plugin_routes

    rebuilt = []
    monkeypatch.setattr(agent_manager, "invalidate_agent", lambda: rebuilt.append(1))
    app = Starlette(
        routes=[
            Route("/plugins", plugin_routes.list_plugins, methods=["GET"]),
            Route(
                "/plugins/{name}/integrations/{integration}/connect",
                plugin_routes.connect_integration,
                methods=["POST"],
            ),
            Route(
                "/plugins/{name}/integrations/{integration}/disconnect",
                plugin_routes.disconnect_integration,
                methods=["POST"],
            ),
        ]
    )
    client = TestClient(app)
    base = "/plugins/github/integrations/github"

    assert client.post(f"{base}/connect", json={}).status_code == 400
    response = client.post(f"{base}/connect", json={"token": " github_pat_x "})
    assert response.status_code == 200 and response.json()["connected"] is True
    # The token is stored, trimmed, and never echoed back.
    assert "github_pat_x" in secrets.values.values()
    assert "github_pat_x" not in client.get("/plugins").text

    response = client.post(f"{base}/disconnect")
    assert response.json()["connected"] is False
    assert "github_pat_x" not in secrets.values.values()
    assert rebuilt == [1, 1]
    assert client.post("/plugins/nope/integrations/x/connect").status_code == 404
