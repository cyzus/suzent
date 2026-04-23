"""
Unit tests for the CLI subcommands (nodes, agent, config).
"""

from unittest.mock import AsyncMock, patch, MagicMock

from typer.testing import CliRunner

from suzent.cli import app

runner = CliRunner()


class TestCLIRoot:
    """Verify existing top-level commands still work."""

    def test_help_shows_all_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "start" in result.output
        assert "doctor" in result.output
        assert "upgrade" in result.output
        assert "nodes" in result.output
        assert "agent" in result.output
        assert "config" in result.output


class TestNodesSubcommand:
    """Test the `suzent nodes` subcommands."""

    def test_nodes_help(self):
        result = runner.invoke(app, ["nodes", "--help"])
        assert result.exit_code == 0
        assert "list" in result.output
        assert "status" in result.output
        assert "describe" in result.output
        assert "invoke" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_list_empty(self, mock_get_client):
        client = MagicMock()
        client.nodes.list = AsyncMock(return_value={"nodes": [], "count": 0})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "list"])
        assert result.exit_code == 0
        assert "No nodes connected" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_list_with_nodes(self, mock_get_client):
        client = MagicMock()
        client.nodes.list = AsyncMock(
            return_value={
                "nodes": [
                    {
                        "node_id": "abc-123",
                        "display_name": "MyPhone",
                        "platform": "ios",
                        "status": "connected",
                        "capabilities": [
                            {"name": "camera.snap", "description": "Take photo"}
                        ],
                    }
                ],
                "count": 1,
            }
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "list"])
        assert result.exit_code == 0
        assert "MyPhone" in result.output
        assert "ios" in result.output
        assert "camera.snap" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_status(self, mock_get_client):
        client = MagicMock()
        client.nodes.list = AsyncMock(
            return_value={
                "nodes": [
                    {"display_name": "Phone", "platform": "ios", "status": "connected"},
                    {
                        "display_name": "Laptop",
                        "platform": "desktop",
                        "status": "disconnected",
                    },
                ]
            }
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "status"])
        assert result.exit_code == 0
        assert "1/2 connected" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_describe(self, mock_get_client):
        client = MagicMock()
        client.nodes.describe = AsyncMock(
            return_value={
                "node_id": "abc-123",
                "display_name": "Phone",
                "platform": "ios",
                "status": "connected",
                "connected_at": "2026-02-17T20:00:00",
                "capabilities": [
                    {
                        "name": "camera.snap",
                        "description": "Take photo",
                        "params_schema": {"format": "str"},
                    }
                ],
            }
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "describe", "abc-123"])
        assert result.exit_code == 0
        assert "Phone" in result.output
        assert "camera.snap" in result.output
        assert "format" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_invoke_success(self, mock_get_client):
        client = MagicMock()
        client.nodes.invoke = AsyncMock(
            return_value={"success": True, "result": {"message": "done"}}
        )
        mock_get_client.return_value = client

        result = runner.invoke(
            app,
            ["nodes", "invoke", "my-node", "echo.test", "--params", '{"msg":"hi"}'],
        )
        assert result.exit_code == 0
        assert "done" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_invoke_failure(self, mock_get_client):
        client = MagicMock()
        client.nodes.invoke = AsyncMock(
            return_value={"success": False, "error": "Not found"}
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "invoke", "my-node", "bad.cmd"])
        assert result.exit_code == 1
        assert "Not found" in result.output

    def test_nodes_invoke_invalid_json(self):
        result = runner.invoke(
            app,
            ["nodes", "invoke", "my-node", "test", "--params", "not-json"],
        )
        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_invoke_key_value(self, mock_get_client):
        captured = {}

        async def fake_invoke(node_id, capability, params=None):
            captured["params"] = params
            return {"success": True, "result": "ok"}

        client = MagicMock()
        client.nodes.invoke = fake_invoke
        mock_get_client.return_value = client

        result = runner.invoke(
            app,
            [
                "nodes",
                "invoke",
                "my-node",
                "test.cmd",
                "text=hello",
                "count=5",
                "score=4.5",
                "verbose=true",
                "debug=False",
                "flag",
                'config={"a":1}',
            ],
        )

        assert result.exit_code == 0
        params = captured["params"]

        assert params["text"] == "hello"
        assert params["count"] == 5
        assert params["score"] == 4.5
        assert params["verbose"] is True
        assert params["debug"] is False
        assert params["flag"] is True
        assert params["config"] == {"a": 1}


class TestAgentSubcommand:
    """Test the `suzent agent` subcommands."""

    def test_agent_help(self):
        result = runner.invoke(app, ["agent", "--help"])
        assert result.exit_code == 0
        assert "chat" in result.output
        assert "status" in result.output

    @patch("suzent.cli.agent.get_client")
    @patch("prompt_toolkit.PromptSession")
    def test_agent_chat(self, mock_prompt_session, mock_get_client):
        import json

        async def fake_stream(payload):
            events = [
                b"data: "
                + json.dumps(
                    {"type": "TEXT_MESSAGE_CONTENT", "delta": "Hello! I'm suzent"}
                ).encode()
                + b"\n\n",
                b"data: " + json.dumps({"type": "AGENT_FINISHED"}).encode() + b"\n\n",
            ]
            for e in events:
                yield e

        # PromptSession.prompt raises EOFError after first call to end the REPL
        session_instance = MagicMock()
        session_instance.prompt.side_effect = EOFError
        mock_prompt_session.return_value = session_instance

        client = MagicMock()
        client.chat.create_chat = AsyncMock(return_value={"id": "test-chat-123"})
        client.chat.stream_message = fake_stream
        client.chat.commands = AsyncMock(return_value={"commands": []})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["agent", "chat", "Hello"])
        assert result.exit_code == 0
        assert "Hello! I'm suzent" in result.output

    @patch("suzent.cli.agent.get_client")
    def test_agent_status_running(self, mock_get_client):
        client = MagicMock()
        client.config.get = AsyncMock(
            return_value={
                "title": "Suzent",
                "model_options": ["gemini/gemini-2.5-pro"],
                "tool_options": ["BashTool", "WebSearchTool"],
            }
        )
        client.nodes.list = AsyncMock(return_value={"nodes": []})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["agent", "status"])
        assert result.exit_code == 0
        assert "running" in result.output


class TestConfigSubcommand:
    """Test the `suzent config` subcommands."""

    def test_config_help(self):
        result = runner.invoke(app, ["config", "--help"])
        assert result.exit_code == 0
        assert "show" in result.output
        assert "get" in result.output
        assert "set" in result.output

    @patch("suzent.cli.config.get_client")
    def test_config_show(self, mock_get_client):
        client = MagicMock()
        client.config.get = AsyncMock(return_value={"title": "Suzent", "debug": False})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "Suzent" in result.output

    @patch("suzent.cli.config.get_client")
    def test_config_get(self, mock_get_client):
        client = MagicMock()
        client.config.get = AsyncMock(
            return_value={"title": "MySuzent", "other": "value"}
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["config", "get", "title"])
        assert result.exit_code == 0
        assert "MySuzent" in result.output

    @patch("suzent.cli.config.get_client")
    def test_config_get_not_found(self, mock_get_client):
        client = MagicMock()
        client.config.get = AsyncMock(return_value={"title": "Suzent"})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["config", "get", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("suzent.cli.config.get_client")
    def test_config_set(self, mock_get_client):
        client = MagicMock()
        client.config.update_preferences = AsyncMock(return_value={"status": "ok"})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["config", "set", "title", "NewName"])
        assert result.exit_code == 0
        assert "updated" in result.output
