"""A newly added MCP server waits for the user to switch it on."""

from suzent.core import mcp_store


def test_a_new_server_starts_off(tmp_path, monkeypatch):
    monkeypatch.setattr(mcp_store, "_MCP_FILE", tmp_path / "mcp_servers.json")

    assert mcp_store.add("docs", {"type": "url", "url": "https://example.com/mcp"})
    assert mcp_store.get("docs")["enabled"] is False
    assert mcp_store.as_agent_config()["mcp_enabled"] == {"docs": False}

    mcp_store.set_enabled("docs", True)
    mcp_store.upsert("docs", {"url": "https://example.com/v2"})
    assert mcp_store.get("docs")["enabled"] is True
