"""
Unit tests for the CLI subcommands (nodes, agent, config).
"""

from unittest.mock import patch

from typer.testing import CliRunner

from suzent.cli import app

runner = CliRunner()


class TestCLIRoot:
    """Verify existing top-level commands still work."""

    def test_help_shows_all_commands(self):
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        # Check existing commands
        assert "start" in result.output
        assert "doctor" in result.output
        assert "upgrade" in result.output
        # Check new subgroups
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

    @patch("suzent.cli.nodes._http_get")
    def test_nodes_list_empty(self, mock_get):
        mock_get.return_value = {"nodes": [], "count": 0}
        result = runner.invoke(app, ["nodes", "list"])
        assert result.exit_code == 0
        assert "No nodes connected" in result.output

    @patch("suzent.cli.nodes._http_get")
    def test_nodes_list_with_nodes(self, mock_get):
        mock_get.return_value = {
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
        result = runner.invoke(app, ["nodes", "list"])
        assert result.exit_code == 0
        assert "MyPhone" in result.output
        assert "ios" in result.output
        assert "camera.snap" in result.output

    @patch("suzent.cli.nodes._http_get")
    def test_nodes_status(self, mock_get):
        mock_get.return_value = {
            "nodes": [
                {"display_name": "Phone", "platform": "ios", "status": "connected"},
                {
                    "display_name": "Laptop",
                    "platform": "desktop",
                    "status": "disconnected",
                },
            ]
        }
        result = runner.invoke(app, ["nodes", "status"])
        assert result.exit_code == 0
        assert "1/2 connected" in result.output

    @patch("suzent.cli.nodes._http_get")
    def test_nodes_describe(self, mock_get):
        mock_get.return_value = {
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
        result = runner.invoke(app, ["nodes", "describe", "abc-123"])
        assert result.exit_code == 0
        assert "Phone" in result.output
        assert "camera.snap" in result.output
        assert "format" in result.output

    @patch("suzent.cli.nodes._http_post")
    def test_nodes_invoke_success(self, mock_post):
        mock_post.return_value = {"success": True, "result": {"message": "done"}}
        result = runner.invoke(
            app,
            ["nodes", "invoke", "my-node", "echo.test", "--params", '{"msg":"hi"}'],
        )
        assert result.exit_code == 0
        assert "done" in result.output

    @patch("suzent.cli.nodes._http_post")
    def test_nodes_invoke_failure(self, mock_post):
        mock_post.return_value = {"success": False, "error": "Not found"}
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

    @patch("suzent.cli.nodes._http_post")
    def test_nodes_invoke_key_value(self, mock_post):
        mock_post.return_value = {"success": True, "result": "ok"}

        # Test mixed types: string, int, float, bool, json, flag
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
        mock_post.assert_called_once()
        args = mock_post.call_args[1]
        params = args["data"]["params"]

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

    @patch("suzent.cli._http._http_post_stream")
    def test_agent_chat(self, mock_post_stream):
        import json

        # Mock the stream iterator with SSE lines
        mock_post_stream.return_value = iter(
            [
                b"data: "
                + json.dumps(
                    {"type": "stream_delta", "data": {"content": "Hello! "}}
                ).encode()
                + b"\n",
                b"data: "
                + json.dumps(
                    {"type": "stream_delta", "data": {"content": "I'm "}}
                ).encode()
                + b"\n",
                b"data: "
                + json.dumps(
                    {"type": "stream_delta", "data": {"content": "suzent"}}
                ).encode()
                + b"\n",
                b"data: "
                + json.dumps(
                    {"type": "final_answer", "data": "Hello! I'm suzent"}
                ).encode()
                + b"\n",
            ]
        )

        result = runner.invoke(app, ["agent", "chat", "Hello"])
        assert result.exit_code == 0
        assert "Hello! I'm suzent" in result.output

    @patch("suzent.cli.agent._http_get")
    def test_agent_status_running(self, mock_get):
        def side_effect(path):
            if path == "/config":
                return {
                    "title": "Suzent",
                    "model_options": ["gemini/gemini-2.5-pro"],
                    "tool_options": ["BashTool", "WebSearchTool"],
                }
            elif path == "/nodes":
                return {"nodes": []}
            return {}

        mock_get.side_effect = side_effect
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

    @patch("suzent.cli.config._http_get")
    def test_config_show(self, mock_get):
        mock_get.return_value = {"title": "Suzent", "debug": False}
        result = runner.invoke(app, ["config", "show"])
        assert result.exit_code == 0
        assert "Suzent" in result.output

    @patch("suzent.cli.config._http_get")
    def test_config_get(self, mock_get):
        mock_get.return_value = {"title": "MySuzent", "other": "value"}
        result = runner.invoke(app, ["config", "get", "title"])
        assert result.exit_code == 0
        assert "MySuzent" in result.output

    @patch("suzent.cli.config._http_get")
    def test_config_get_not_found(self, mock_get):
        mock_get.return_value = {"title": "Suzent"}
        result = runner.invoke(app, ["config", "get", "nonexistent"])
        assert result.exit_code == 1
        assert "not found" in result.output

    @patch("suzent.cli.config._http_post")
    def test_config_set(self, mock_post):
        mock_post.return_value = {"status": "ok"}
        result = runner.invoke(app, ["config", "set", "title", "NewName"])
        assert result.exit_code == 0
        assert "Set title" in result.output
