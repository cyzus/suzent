"""
Unit tests for the local node host.
"""

import json

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from suzent.nodes.node_host import (
    NodeHost,
    _HANDLERS,
    handle_speaker_speak,
    handle_camera_snap,
)


class TestCapabilityDecorator:
    """Test the @capability decorator."""

    def test_handler_registered(self):
        assert "speaker.speak" in _HANDLERS
        assert "camera.snap" in _HANDLERS

    def test_handler_metadata(self):
        meta = _HANDLERS["speaker.speak"]._capability_meta
        assert meta["name"] == "speaker.speak"
        assert "text-to-speech" in meta["description"].lower()
        assert "text" in meta["params_schema"]

    def test_camera_metadata(self):
        meta = _HANDLERS["camera.snap"]._capability_meta
        assert meta["name"] == "camera.snap"
        assert "format" in meta["params_schema"]


class TestNodeHost:
    """Test the NodeHost class."""

    def test_init_defaults(self):
        host = NodeHost()
        assert host.display_name == "Local PC"
        assert host.node_id is None
        assert len(host._handlers) >= 2

    def test_init_capability_filter(self):
        host = NodeHost(capabilities=["speaker.speak"])
        assert "speaker.speak" in host._handlers
        assert "camera.snap" not in host._handlers

    def test_init_custom_name(self):
        host = NodeHost(display_name="My Desktop", platform="linux")
        assert host.display_name == "My Desktop"
        assert host.platform == "linux"

    def test_build_connect_message(self):
        host = NodeHost(display_name="TestNode", platform="test")
        msg = host._build_connect_message()

        assert msg["type"] == "connect"
        assert msg["display_name"] == "TestNode"
        assert msg["platform"] == "test"
        assert len(msg["capabilities"]) >= 2

        cap_names = [c["name"] for c in msg["capabilities"]]
        assert "speaker.speak" in cap_names
        assert "camera.snap" in cap_names

    def test_stop(self):
        host = NodeHost()
        assert host._stop is False
        host.stop()
        assert host._stop is True


class TestHandleInvoke:
    """Test the invoke dispatch logic."""

    @pytest.mark.asyncio
    async def test_unknown_command(self):
        host = NodeHost()
        ws = AsyncMock()

        await host._handle_invoke(
            ws,
            {
                "request_id": "req-1",
                "command": "nonexistent.cmd",
                "params": {},
            },
        )

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["success"] is False
        assert "Unknown command" in sent["error"]
        assert sent["request_id"] == "req-1"

    @pytest.mark.asyncio
    async def test_handler_success(self):
        host = NodeHost()
        ws = AsyncMock()

        # Patch the speaker handler to avoid actual TTS
        with patch.dict(
            host._handlers,
            {"speaker.speak": AsyncMock(return_value={"spoke": "hello"})},
        ):
            await host._handle_invoke(
                ws,
                {
                    "request_id": "req-2",
                    "command": "speaker.speak",
                    "params": {"text": "hello"},
                },
            )

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["success"] is True
        assert sent["result"] == {"spoke": "hello"}

    @pytest.mark.asyncio
    async def test_handler_exception(self):
        host = NodeHost()
        ws = AsyncMock()

        with patch.dict(
            host._handlers,
            {"speaker.speak": AsyncMock(side_effect=RuntimeError("TTS failed"))},
        ):
            await host._handle_invoke(
                ws,
                {
                    "request_id": "req-3",
                    "command": "speaker.speak",
                    "params": {"text": "hi"},
                },
            )

        ws.send.assert_called_once()
        sent = json.loads(ws.send.call_args[0][0])
        assert sent["success"] is False
        assert "TTS failed" in sent["error"]


class TestSpeakerHandler:
    """Test the speaker.speak handler."""

    @pytest.mark.asyncio
    async def test_empty_text_returns_error(self):
        result = await handle_speaker_speak({"text": ""})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_missing_text_returns_error(self):
        result = await handle_speaker_speak({})
        assert "error" in result

    @pytest.mark.asyncio
    @patch("suzent.voice.audio_io.SoundDeviceSink")
    @patch("suzent.voice.speech.SpeechOutput")
    @patch("suzent.config.CONFIG")
    async def test_speak_calls_speech_output(
        self, mock_config, mock_speech_cls, mock_sink_cls
    ):
        mock_config.tts_model = "openai/tts-1"
        mock_config.tts_voice = "alloy"

        mock_sink = MagicMock()
        mock_sink_cls.return_value = mock_sink

        mock_speech = MagicMock()
        mock_speech.speak = AsyncMock()
        mock_speech_cls.return_value = mock_speech

        result = await handle_speaker_speak(
            {"text": "hello world", "prompt": "cheerful"}
        )

        mock_sink_cls.assert_called_once_with(sample_rate=24000)
        mock_speech_cls.assert_called_once()
        mock_speech.speak.assert_called_once_with("hello world", prompt="cheerful")
        mock_sink.close.assert_called_once()
        assert result == {"spoke": "hello world"}


class TestCameraHandler:
    """Test the camera.snap handler."""

    @pytest.mark.asyncio
    @patch("suzent.nodes.node_host.asyncio")
    async def test_snap_returns_file_path(self, mock_asyncio_mod):
        mock_asyncio_mod.to_thread = AsyncMock(return_value="/tmp/suzent_snap_test.png")

        result = await handle_camera_snap({"format": "png"})
        assert result["file"] == "/tmp/suzent_snap_test.png"
        assert result["format"] == "png"

    @pytest.mark.asyncio
    @patch("suzent.nodes.node_host.asyncio")
    async def test_snap_default_format(self, mock_asyncio_mod):
        mock_asyncio_mod.to_thread = AsyncMock(return_value="/tmp/snap.png")

        result = await handle_camera_snap({})
        assert result["format"] == "png"

    @pytest.mark.asyncio
    @patch("suzent.nodes.node_host.asyncio")
    async def test_snap_invalid_format_defaults_to_png(self, mock_asyncio_mod):
        mock_asyncio_mod.to_thread = AsyncMock(return_value="/tmp/snap.png")

        result = await handle_camera_snap({"format": "bmp"})
        assert result["format"] == "png"


class TestNodeHostCLI:
    """Test the `suzent nodes host` CLI command."""

    def test_host_help(self):
        from typer.testing import CliRunner
        from suzent.cli import app

        runner = CliRunner()
        result = runner.invoke(app, ["nodes", "host", "--help"])
        assert result.exit_code == 0
        assert "host" in result.output
        assert "--name" in result.output
        assert "--capabilities" in result.output
