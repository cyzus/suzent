#!/usr/bin/env python3
"""
A Suzent node in ~100 lines, with **no Suzent dependency**.

Joining the mesh does not require running Suzent. A node is any device that
speaks a small JSON-over-WebSocket protocol, so a TV, a doorbell, a phone, or a
bridge script can advertise capabilities your agent can invoke.

Run it:

    pip install websockets
    python minimal_node.py --name "Living Room TV" --url ws://192.168.1.10:25314/ws/node

On first connect the server replies ``pending`` with a pairing code and waits
for the operator to approve the device in Suzent (Settings → Devices). Once
approved you receive a durable ``device_token``; save it and pass it next time
with --token to reconnect silently.

── Protocol ────────────────────────────────────────────────────────────
  → {"type":"connect","display_name":...,"platform":...,"capabilities":[...],
     "device_token":"<optional, from a previous approval>"}
  ← {"type":"pending","pairing_code":"ABC123"}     (new device, awaiting approval)
  ← {"type":"connected","node_id":...,"device_token":...}
  ← {"type":"invoke","request_id":...,"command":"tv.play","params":{...}}
  → {"type":"result","request_id":...,"success":true,"result":{...}}
  ← {"type":"ping"}  →  {"type":"pong"}
────────────────────────────────────────────────────────────────────────
"""

import argparse
import asyncio
import json
import platform

import websockets

# ─── Your device's capabilities ──────────────────────────────────────
# Each entry is one thing the agent may invoke. Keep names namespaced
# ("tv.play", not "play") so they stay unambiguous across a mesh.

CAPABILITIES = [
    {
        "name": "tv.play",
        "description": "Play a title on this TV",
        "params_schema": {"title": "str"},
    },
    {
        "name": "tv.volume",
        "description": "Set the volume (0-100)",
        "params_schema": {"level": "int"},
    },
]


async def handle_invoke(command: str, params: dict) -> dict:
    """Run one command. Replace these bodies with real device calls.

    For a TV this is typically where you'd talk to the vendor's own API —
    Roku ECP, LG webOS, Chromecast, or ADB — which is why a bridge script on an
    always-on machine is often more practical than code running on the TV.
    """
    if command == "tv.play":
        title = params.get("title", "")
        print(f"[device] playing {title!r}")
        return {"playing": title}

    if command == "tv.volume":
        level = int(params.get("level", 0))
        print(f"[device] volume -> {level}")
        return {"volume": level}

    raise ValueError(f"Unknown command: {command}")


async def run(url: str, name: str, token: str) -> None:
    async with websockets.connect(url) as ws:
        await ws.send(
            json.dumps(
                {
                    "type": "connect",
                    "display_name": name,
                    "platform": platform.system().lower(),
                    "capabilities": CAPABILITIES,
                    "device_token": token,
                }
            )
        )

        async for raw in ws:
            message = json.loads(raw)
            kind = message.get("type")

            if kind == "pending":
                print(
                    f"[pairing] approve this device in Suzent. "
                    f"Pairing code: {message.get('pairing_code')}"
                )

            elif kind == "connected":
                issued = message.get("device_token") or ""
                print(f"[connected] node_id={message.get('node_id')}")
                if issued:
                    print(f"[connected] save this token and reuse it: {issued}")

            elif kind == "ping":
                await ws.send(json.dumps({"type": "pong"}))

            elif kind == "invoke":
                request_id = message.get("request_id")
                try:
                    result = await handle_invoke(
                        message.get("command", ""), message.get("params") or {}
                    )
                    reply = {"success": True, "result": result}
                except Exception as exc:
                    # Always answer an invoke — a silent node just times out.
                    reply = {"success": False, "error": f"{type(exc).__name__}: {exc}"}
                await ws.send(
                    json.dumps({"type": "result", "request_id": request_id, **reply})
                )

            elif kind == "error":
                print(f"[error] {message.get('message')}")
                return


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal Suzent node")
    parser.add_argument("--url", default="ws://127.0.0.1:25314/ws/node")
    parser.add_argument("--name", default="Minimal Node")
    parser.add_argument(
        "--token", default="", help="device_token from a prior approval"
    )
    args = parser.parse_args()

    try:
        asyncio.run(run(args.url, args.name, args.token))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
