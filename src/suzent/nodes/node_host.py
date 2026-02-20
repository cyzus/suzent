"""
Local node host — connects to the Suzent server as a node and exposes
device capabilities (speaker, camera) via the WebSocket protocol.

Usage:
    python -m suzent.nodes.node_host --name "My PC"
    suzent nodes host --name "My PC"
"""

import asyncio
import json
import logging
import signal
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Coroutine

import websockets

logger = logging.getLogger(__name__)

# ─── Default config ──────────────────────────────────────────────────

DEFAULT_GATEWAY_URL = "ws://localhost:25314/ws/node"
DEFAULT_DISPLAY_NAME = "Local PC"
DEFAULT_PLATFORM = sys.platform
RECONNECT_DELAY = 5  # seconds between reconnect attempts


# ─── Capability handlers ─────────────────────────────────────────────

_HANDLERS: dict[str, Callable[..., Coroutine[Any, Any, dict[str, Any]]]] = {}


def capability(
    name: str,
    description: str = "",
    params_schema: dict[str, str] | None = None,
):
    """Decorator to register a command handler as a node capability."""

    def decorator(fn: Callable[..., Coroutine[Any, Any, dict[str, Any]]]):
        fn._capability_meta = {  # type: ignore[attr-defined]
            "name": name,
            "description": description,
            "params_schema": params_schema or {},
        }
        _HANDLERS[name] = fn
        return fn

    return decorator


# ─── Built-in handlers ───────────────────────────────────────────────


@capability(
    name="speaker.speak",
    description="Speak text aloud using text-to-speech on the local speakers",
    params_schema={
        "text": "(required) The text content to speak aloud",
        "prompt": "(optional) Describe the emotion and tone, e.g. 'cheerful and warm'",
    },
)
async def handle_speaker_speak(params: dict[str, Any]) -> dict[str, Any]:
    """Use local TTS to speak text through the system speakers."""
    text = params.get("text", "")
    prompt = params.get("prompt", "")

    if not text:
        return {"error": "No text provided"}

    from suzent.config import CONFIG
    from suzent.voice.audio_io import SoundDeviceSink
    from suzent.voice.speech import SpeechOutput

    tts_model = CONFIG.tts_model or "openai/tts-1"
    tts_voice = CONFIG.tts_voice or "alloy"

    sink = SoundDeviceSink(sample_rate=24000)
    try:
        speech = SpeechOutput(
            audio_sink=sink,
            tts_model=tts_model,
            tts_voice=tts_voice,
            output_rate=24000,
        )
        await speech.speak(text, prompt=prompt)
        return {"spoke": text}
    finally:
        sink.close()


@capability(
    name="camera.snap",
    description="Capture a photo from the default webcam and save to a temp file",
    params_schema={
        "format": "(optional) Image format: 'png' or 'jpg' (default: png)",
    },
)
async def handle_camera_snap(params: dict[str, Any]) -> dict[str, Any]:
    """Capture a frame from the default camera."""
    fmt = params.get("format", "png")
    if fmt not in ("png", "jpg", "jpeg"):
        fmt = "png"

    def _capture() -> str:
        import cv2

        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            raise RuntimeError("Cannot open camera")
        try:
            ret, frame = cap.read()
            if not ret:
                raise RuntimeError("Failed to capture frame")

            suffix = ".jpg" if fmt in ("jpg", "jpeg") else ".png"
            path = Path(tempfile.mktemp(suffix=suffix, prefix="suzent_snap_"))
            cv2.imwrite(str(path), frame)
            return str(path)
        finally:
            cap.release()

    path = await asyncio.to_thread(_capture)
    return {"file": path, "format": fmt}


# ─── Node host core ──────────────────────────────────────────────────


class NodeHost:
    """WebSocket client that connects to Suzent as a local node.

    Args:
        gateway_url: WebSocket URL of the Suzent server node endpoint.
        display_name: Human-readable name for this node.
        platform: Platform identifier (e.g., "win32", "darwin", "linux").
        capabilities: List of capability names to advertise. If None, all
            registered handlers are advertised.
    """

    def __init__(
        self,
        gateway_url: str = DEFAULT_GATEWAY_URL,
        display_name: str = DEFAULT_DISPLAY_NAME,
        platform: str = DEFAULT_PLATFORM,
        capabilities: list[str] | None = None,
    ):
        self.gateway_url = gateway_url
        self.display_name = display_name
        self.platform = platform
        self._stop = False
        self._node_id: str | None = None

        # Filter handlers to requested capabilities
        if capabilities:
            self._handlers = {k: v for k, v in _HANDLERS.items() if k in capabilities}
        else:
            self._handlers = dict(_HANDLERS)

    @property
    def node_id(self) -> str | None:
        return self._node_id

    def _build_connect_message(self) -> dict[str, Any]:
        """Build the handshake message."""
        caps = []
        for fn in self._handlers.values():
            meta = fn._capability_meta  # type: ignore[attr-defined]
            caps.append(
                {
                    "name": meta["name"],
                    "description": meta["description"],
                    "params_schema": meta["params_schema"],
                }
            )

        return {
            "type": "connect",
            "display_name": self.display_name,
            "platform": self.platform,
            "capabilities": caps,
        }

    async def _handle_invoke(self, ws, data: dict[str, Any]) -> None:
        """Dispatch an invoke message to the matching handler."""
        request_id = data.get("request_id", "")
        command = data.get("command", "")
        params = data.get("params", {})

        handler = self._handlers.get(command)
        if not handler:
            await ws.send(
                json.dumps(
                    {
                        "type": "result",
                        "request_id": request_id,
                        "success": False,
                        "error": f"Unknown command: {command}",
                    }
                )
            )
            return

        try:
            logger.info(f"⚡ Invoking {command}")
            result = await handler(params)
            await ws.send(
                json.dumps(
                    {
                        "type": "result",
                        "request_id": request_id,
                        "success": True,
                        "result": result,
                    }
                )
            )
        except Exception as e:
            logger.error(f"Handler error for {command}: {e}")
            await ws.send(
                json.dumps(
                    {
                        "type": "result",
                        "request_id": request_id,
                        "success": False,
                        "error": str(e),
                    }
                )
            )

    async def run_once(self) -> None:
        """Connect, handshake, and run the message loop until disconnect."""
        logger.info(f"🔌 Connecting to {self.gateway_url} ...")

        async with websockets.connect(self.gateway_url) as ws:
            # Handshake
            await ws.send(json.dumps(self._build_connect_message()))
            resp = json.loads(await ws.recv())

            if resp.get("type") == "error":
                raise ConnectionError(f"Handshake rejected: {resp.get('error')}")

            self._node_id = resp.get("node_id")
            cap_names = ", ".join(self._handlers.keys())
            logger.info(
                f"✅ Connected as '{self.display_name}' "
                f"(id={self._node_id}, capabilities=[{cap_names}])"
            )

            # Message loop
            async for message in ws:
                if self._stop:
                    break

                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "invoke":
                    await self._handle_invoke(ws, data)
                elif msg_type == "ping":
                    await ws.send(json.dumps({"type": "pong"}))
                else:
                    logger.debug(f"Unhandled message type: {msg_type}")

    async def run(self) -> None:
        """Run with automatic reconnection."""
        while not self._stop:
            try:
                await self.run_once()
            except (ConnectionError, OSError) as e:
                if self._stop:
                    break
                logger.warning(
                    f"⚠️  Disconnected: {e}. Reconnecting in {RECONNECT_DELAY}s..."
                )
                await asyncio.sleep(RECONNECT_DELAY)
            except websockets.exceptions.ConnectionClosed as e:
                if self._stop:
                    break
                logger.warning(
                    f"⚠️  Connection closed: {e}. Reconnecting in {RECONNECT_DELAY}s..."
                )
                await asyncio.sleep(RECONNECT_DELAY)

        logger.info("🛑 Node host stopped.")

    def stop(self) -> None:
        """Signal the host to stop."""
        self._stop = True


# ─── CLI entry point ─────────────────────────────────────────────────


def main():
    """Start the node host from the command line."""
    import argparse

    parser = argparse.ArgumentParser(description="Suzent local node host")
    parser.add_argument("--name", default=DEFAULT_DISPLAY_NAME, help="Display name")
    parser.add_argument("--url", default=DEFAULT_GATEWAY_URL, help="Gateway WS URL")
    parser.add_argument(
        "--capabilities",
        default=None,
        help="Comma-separated capability filter (default: all)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    caps = args.capabilities.split(",") if args.capabilities else None
    host = NodeHost(
        gateway_url=args.url,
        display_name=args.name,
        capabilities=caps,
    )

    # Graceful shutdown on Ctrl+C
    def _signal_handler(sig, frame):
        logger.info("Shutting down...")
        host.stop()

    signal.signal(signal.SIGINT, _signal_handler)

    asyncio.run(host.run())


if __name__ == "__main__":
    main()
