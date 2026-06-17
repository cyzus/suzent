# Suzent Nodes Guide

This guide covers the node system in Suzent — how to connect companion devices and control them remotely.

## Overview

Nodes are companion devices (phones, desktops, headless servers) that connect to the Suzent server via WebSocket and expose capabilities the agent can invoke remotely. Inspired by OpenClaw's distributed control architecture.

### Key Concepts

| Concept | Description |
|---------|-------------|
| **Node** | A connected device that advertises capabilities |
| **Capability** | A named command a node can handle (e.g., `camera.snap`) |
| **NodeManager** | Server-side registry that tracks and dispatches to nodes |
| **WebSocketNode** | Node implementation using WebSocket + JSON-RPC protocol |

## Architecture

```
┌───────────────────┐     WebSocket       ┌───────────────────┐
│  Companion Node   │◄──────────────────► │   Suzent Server   │
│  (Phone/Desktop)  │   JSON-RPC msgs     │   (NodeManager)   │
└───────────────────┘                     └──────┬────────────┘
                                                 │ REST API
                                          ┌──────▼────────────┐
                                          │  CLI / REST Agent │
                                          │ suzent nodes / API│
                                          └───────────────────┘
```

### Sandbox Python Example

```python
import os
import requests

base = os.environ["SUZENT_BASE_URL"]

# List nodes
nodes = requests.get(f"{base}/nodes", timeout=30).json().get("nodes", [])
if not nodes:
    raise RuntimeError("No nodes connected")

# Resolve by display name (recommended)
target_name = "MyPhone"
target = next((n for n in nodes if n.get("display_name") == target_name), nodes[0])
node_id = target["node_id"]

# Describe
detail = requests.get(f"{base}/nodes/{node_id}", timeout=30).json()

# Invoke
resp = requests.post(
    f"{base}/nodes/{node_id}/invoke",
    json={"command": "camera.snap", "params": {"format": "png"}},
    timeout=60,
)
resp.raise_for_status()
print(resp.json())
```

## Using Nodes via CLI (Host Mode)

Nodes are controlled through the `suzent node` CLI subcommands. The agent uses these same commands via `BashTool`.

### List Connected Nodes

```bash
suzent node list
```

### Check Connectivity

```bash
suzent node status
```

### Describe a Node's Capabilities

```bash
suzent node describe <node_id_or_name>
```

### Invoke a Command

```bash
# Option 1: Key-Value Pairs (Simpler)
suzent node invoke <node> <command> key=value [key2=value2 ...]

# Option 2: JSON Params (Legacy/Complex)
suzent node invoke <node> <command> --params '{"key": "value"}'
```

**Examples:**

```bash
# Take a photo (simple)
suzent node invoke MyPhone camera.snap format=png

# Speak with arguments (inferred types)
suzent node invoke "Local PC" speaker.speak text="Hello world" prompt=cheerful

# Mixed types (int, boolean)
suzent node invoke MyNode some.command count=5 verbose=true

# JSON fallback for complex objects
suzent node invoke MyNode config.update data='{"nested": true}'
```

## WebSocket Protocol

Nodes connect to the server at `ws://<host>:<port>/ws/node` and follow a JSON-RPC-style message protocol.

### 1. Handshake

**Node → Server** (on connect):
```json
{
  "type": "connect",
  "display_name": "MyPhone",
  "platform": "ios",
  "capabilities": [
    {
      "name": "camera.snap",
      "description": "Take a photo with the device camera",
      "params_schema": {"format": "str", "quality": "float"}
    }
  ],
  "auth_token": "",
  "device_token": ""
}
```

`auth_token` is checked only in `token` mode. `device_token` is a durable token
from a prior `approve`-mode approval; when valid it connects silently.

**Server → Node** (acknowledgment):
```json
{
  "type": "connected",
  "node_id": "a1b2c3d4-...",
  "device_token": ""
}
```

In `approve` mode, a node the server has not seen first receives a
`{"type": "pending", "pairing_code": "ABC123"}` message and waits; on approval
it gets the `connected` message above with a freshly-minted `device_token` to
persist. On rejection/timeout it receives `{"type": "error", "message": "..."}`.

### 2. Command Invocation

**Server → Node**:
```json
{
  "type": "invoke",
  "request_id": "uuid-...",
  "command": "camera.snap",
  "params": {"format": "png"}
}
```

**Node → Server**:
```json
{
  "type": "result",
  "request_id": "uuid-...",
  "success": true,
  "result": {"file": "/tmp/photo.png"}
}
```

### 3. Heartbeat

**Server → Node**: `{"type": "ping"}`
**Node → Server**: `{"type": "pong"}`

## Building a Node Client

To connect a device as a node, implement a WebSocket client that:

1. Connects to `ws://<suzent-host>:25314/ws/node`
2. Sends a `connect` message with capabilities
3. Waits for `connected` acknowledgment
4. Listens for `invoke` messages and responds with `result` messages

### Python Example

```python
import asyncio
import json
import websockets

async def run_node():
    uri = "ws://localhost:25314/ws/node"
    async with websockets.connect(uri) as ws:
        # Handshake
        await ws.send(json.dumps({
            "type": "connect",
            "display_name": "MyDevice",
            "platform": "python",
            "capabilities": [
                {"name": "echo", "description": "Echo back a message"},
            ]
        }))

        resp = json.loads(await ws.recv())
        print(f"Connected as {resp['node_id']}")

        # Message loop
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "invoke":
                # Handle the command
                result = {"echo": data["params"].get("text", "")}
                await ws.send(json.dumps({
                    "type": "result",
                    "request_id": data["request_id"],
                    "success": True,
                    "result": result,
                }))
            elif data["type"] == "ping":
                await ws.send(json.dumps({"type": "pong"}))

asyncio.run(run_node())
```

## Peer agents (`agent.run`)

A node host advertises an `agent.run` capability that runs a prompt through
**that device's own Suzent agent** (its own files, memory, tools) and returns
the final reply. This is what lets each device be both a host and a node and
**trigger another linked device's agent**:

```bash
# From device A, delegate a task to device B's agent:
suzent node invoke "Device B" agent.run prompt="summarize ~/notes" --timeout 300
```

Agent runs can take minutes, so pass `--timeout` (the REST `invoke` body also
accepts a `timeout` field). The node host reaches its own local server's
`/chat` endpoint; override that base URL with `suzent node host --server-url`.

## Authentication

Connections are gated by `node_auth_mode`. A device that has been approved once
receives a **durable per-device token** and reconnects silently thereafter.

| Mode | Behavior |
|------|----------|
| `open` (default) | Any device that can reach the server may connect. Use only on a trusted/loopback network. |
| `token` | The node must present a shared secret (`node_auth_token`) in its handshake. One key for a mesh you fully control. |
| `approve` | A new device is parked as **pending** and an operator must approve it. On approval the server mints a durable per-device token the node persists and reuses; revoke it per-device to force re-pairing. |

> ⚠️ **Plaintext transport.** `ws://` traffic is unencrypted — the token only
> protects you on a trusted network or over `wss://`/a tunnel. `agent.run` is
> effectively authenticated remote code execution, so never expose an `open`
> server (or your token) on an untrusted network.

### Token mode

```bash
# On the server, set the shared secret (stored in machine-local config):
# (or use the Devices settings tab → Connection auth → Regenerate)
suzent config set node_auth_mode token

# On each companion device:
suzent node host --name "My Laptop" --token <shared-secret>
# or: SUZENT_NODE_TOKEN=<shared-secret> suzent node host --name "My Laptop"
```

### Approve mode (pairing + durable tokens)

```bash
# Server in approve mode:
suzent config set node_auth_mode approve

# Companion device connects and prints a pairing code, then waits:
suzent node host --name "My Laptop"

# On the server, approve it (mints a durable per-device token):
suzent node pending                # list codes awaiting approval
suzent node approve <pairing_code>

# Manage durable devices:
suzent node devices                # list approved devices
suzent node revoke <device_id>     # revoke; device must re-pair
```

The node persists its minted token under the user config dir
(`node_host_devices.json`, keyed by gateway URL) and presents it on reconnect,
so approval is a one-time step. The server stores the durable tokens in
`node_devices.json`.

### REST / Devices tab

The same actions are available via REST (`GET /nodes/pending`,
`POST /nodes/pending/{code}/approve|deny`, `GET /nodes/devices`,
`POST /nodes/devices/{device_id}/revoke`, and `GET|POST /nodes/config`) and via
**Settings → Devices**, which lists connected nodes (with an **Agent** badge for
`agent.run`-capable devices), pending approvals, durable devices, and the auth
mode/token.

## Configuration

Node system settings in Suzent configuration:

| Field | Default | Description |
|-------|---------|-------------|
| `nodes_enabled` | `true` | Enable/disable node WebSocket connections |
| `node_auth_mode` | `"open"` | Authentication mode: `open`, `token`, or `approve` |
| `node_auth_token` | `""` | Shared secret required in `token` mode (machine-local) |

Modify via CLI:
```bash
suzent config get nodes_enabled
suzent config set nodes_enabled true
```

## Pydantic Models

All protocol messages and API schemas are defined as Pydantic models in `src/suzent/nodes/models.py`:

- **Protocol**: `ConnectMessage`, `ConnectedResponse`, `InvokeMessage`, `ResultMessage`, `PingMessage`, `PongMessage`, `EventMessage`, `ErrorResponse`
- **API**: `NodeInfo`, `NodeListResponse`, `InvokeRequest`, `InvokeResponse`, `CapabilitySchema`

## Troubleshooting

### Node disconnects immediately
Check that the `connect` message has valid JSON with required `display_name` field. Review server logs for handshake errors.

### Command timeout
Default timeout is 30 seconds. Ensure the node client sends a `result` message with the matching `request_id` promptly.
