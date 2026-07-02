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
        assert "update" in result.output
        assert "upgrade" in result.output
        assert "check-update" in result.output
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
        client.nodes.peers = AsyncMock(return_value={"peers": [], "count": 0})
        client.nodes.devices = AsyncMock(return_value={"devices": [], "count": 0})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "list"])
        assert result.exit_code == 0
        assert "No nodes or linked devices" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_list_unified(self, mock_get_client):
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
        client.nodes.peers = AsyncMock(
            return_value={
                "peers": [
                    {
                        "peer_id": "p1",
                        "name": "Studio",
                        "base_url": "http://peer.example:25314",
                        "mode": "trigger",
                        "reverse_enabled": True,
                        "online": True,
                    }
                ],
                "count": 1,
            }
        )
        client.nodes.devices = AsyncMock(return_value={"devices": [], "count": 0})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "list"])
        assert result.exit_code == 0
        # WS node
        assert "MyPhone" in result.output and "camera.snap" in result.output
        # control-grant peer, with direction
        assert "Studio" in result.output and "trigger them" in result.output
        assert "inbound granted" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_invoke_routes_to_peer(self, mock_get_client):
        from suzent.client.base import ClientError

        client = MagicMock()
        # invoke on the node manager fails (it's a peer, not a WS node)…
        client.nodes.invoke = AsyncMock(side_effect=ClientError("Node not found: p1"))
        client.nodes.peers = AsyncMock(
            return_value={"peers": [{"peer_id": "p1", "name": "Studio"}]}
        )
        # …so the CLI proxies to the peer and gets a result back.
        client.nodes.invoke_peer = AsyncMock(
            return_value={"success": True, "result": {"spoke": "hi"}}
        )
        mock_get_client.return_value = client

        result = runner.invoke(
            app, ["nodes", "invoke", "Studio", "speaker.speak", "text=hi"]
        )
        assert result.exit_code == 0
        assert "spoke" in result.output
        client.nodes.invoke_peer.assert_awaited_once()

    @patch("suzent.cli.node.get_client")
    def test_nodes_invoke_bare_arg_warns(self, mock_get_client):
        # A bare value (no '=') still works as a boolean flag, but must warn so a
        # forgotten key (`speaker.speak "hi"` → {"hi":True}) is visible.
        captured = {}

        async def fake_invoke(node, command, params, timeout=None):
            captured["params"] = params
            return {"success": True, "result": "ok"}

        client = MagicMock()
        client.nodes.invoke = fake_invoke
        mock_get_client.return_value = client

        result = runner.invoke(
            app, ["nodes", "invoke", "my-node", "speaker.speak", "hi"]
        )
        assert result.exit_code == 0
        assert "no '='" in result.output and 'text="hi"' in result.output
        assert captured["params"] == {"hi": True}

    @patch("suzent.cli.node.get_client")
    def test_nodes_describe_falls_back_to_peer(self, mock_get_client):
        from suzent.client.base import ClientError

        client = MagicMock()
        # Not a WS node…
        client.nodes.describe = AsyncMock(
            side_effect=ClientError("Server error (404): Node not found: MacBook Pro")
        )
        # …but a linked peer, so describe shows peer info (both directions).
        client.nodes.peers = AsyncMock(
            return_value={
                "peers": [
                    {
                        "peer_id": "fd12",
                        "name": "MacBook Pro",
                        "base_url": "http://peer.example:25314",
                        "mode": "trigger",
                        "reverse_enabled": True,
                        "online": True,
                    }
                ]
            }
        )
        client.nodes.peer_capabilities = AsyncMock(
            return_value={
                "capabilities": [
                    {
                        "name": "speaker.speak",
                        "description": "Speak",
                        "node": "Mac",
                        "params_schema": {"text": "(required) The text to speak"},
                    },
                    {"name": "camera.snap", "description": "Snap", "node": "Mac"},
                ],
                "count": 2,
            }
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "describe", "MacBook Pro"])
        assert result.exit_code == 0
        assert "Peer: MacBook Pro" in result.output
        assert "trigger them" in result.output
        assert "granted" in result.output
        # Live-fetched capabilities are listed, with their param keys.
        assert "speaker.speak" in result.output
        assert "camera.snap" in result.output
        assert "text: (required) The text to speak" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_describe_peer_caps_unreachable(self, mock_get_client):
        from suzent.client.base import ClientError

        client = MagicMock()
        client.nodes.describe = AsyncMock(
            side_effect=ClientError("Server error (404): Node not found: Mac")
        )
        client.nodes.peers = AsyncMock(
            return_value={
                "peers": [
                    {
                        "peer_id": "p1",
                        "name": "Mac",
                        "base_url": "http://h:1",
                        "mode": "trigger",
                        "reverse_enabled": False,
                        "online": False,
                    }
                ]
            }
        )
        # Peer offline → capabilities fetch fails; describe still succeeds.
        client.nodes.peer_capabilities = AsyncMock(
            side_effect=ClientError("Server error (502): Couldn't reach peer")
        )
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "describe", "Mac"])
        assert result.exit_code == 0
        assert "Peer: Mac" in result.output
        assert "unavailable" in result.output.lower()

    @patch("suzent.cli.node.get_client")
    def test_nodes_describe_unknown(self, mock_get_client):
        from suzent.client.base import ClientError

        client = MagicMock()
        client.nodes.describe = AsyncMock(
            side_effect=ClientError("Server error (404): Node not found: ghost")
        )
        client.nodes.peers = AsyncMock(return_value={"peers": []})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "describe", "ghost"])
        assert result.exit_code == 1
        assert "No node or peer matching" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_trigger_streams_reply(self, mock_get_client):
        client = MagicMock()
        client.nodes.peers = AsyncMock(
            return_value={
                "peers": [{"peer_id": "p1", "name": "Studio", "base_url": "http://h:1"}]
            }
        )

        async def fake_trigger(peer_id, prompt, chat_id=None):
            assert peer_id == "p1"
            yield b'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"Hi "}\n\n'
            yield b'data: {"type":"TEXT_MESSAGE_CONTENT","delta":"there"}\n\n'
            yield b"data: [DONE]\n\n"

        client.nodes.trigger = fake_trigger
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "trigger", "Studio", "hello"])
        assert result.exit_code == 0
        assert "Hi there" in result.output

    @patch("suzent.cli.node.get_client")
    def test_nodes_trigger_unknown_peer(self, mock_get_client):
        client = MagicMock()
        client.nodes.peers = AsyncMock(return_value={"peers": []})
        mock_get_client.return_value = client

        result = runner.invoke(app, ["nodes", "trigger", "ghost", "hi"])
        assert result.exit_code == 1
        assert "No peer" in result.output

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

        async def fake_invoke(node_id, capability, params=None, timeout=None):
            captured["params"] = params
            captured["timeout"] = timeout
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
