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

## Using Nodes in Sandbox (REST API)

In sandbox mode, `suzent` CLI is not installed. Use `SUZENT_BASE_URL` and call the REST API directly.

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/nodes` | List all connected nodes |
| GET | `/nodes/{node_id_or_name}` | Describe a specific node |
| POST | `/nodes/{node_id_or_name}/invoke` | Invoke a command on a node |
| WS | `/ws/node` | WebSocket endpoint for node connections |

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

Nodes are controlled through the `suzent nodes` CLI subcommands. The agent uses these same commands via `BashTool`.

### List Connected Nodes

```bash
suzent nodes list
```

### Check Connectivity

```bash
suzent nodes status
```

### Describe a Node's Capabilities

```bash
suzent nodes describe <node_id_or_name>
```

### Invoke a Command

```bash
# Option 1: Key-Value Pairs (Simpler)
suzent nodes invoke <node> <command> key=value [key2=value2 ...]

# Option 2: JSON Params (Legacy/Complex)
suzent nodes invoke <node> <command> --params '{"key": "value"}'
```

**Examples:**

```bash
# Take a photo (simple)
suzent nodes invoke MyPhone camera.snap format=png

# Speak with arguments (inferred types)
suzent nodes invoke "Local PC" speaker.speak text="Hello world" prompt=cheerful

# Mixed types (int, boolean)
suzent nodes invoke MyNode some.command count=5 verbose=true

# JSON fallback for complex objects
suzent nodes invoke MyNode config.update data='{"nested": true}'
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
  ]
}
```

**Server → Node** (acknowledgment):
```json
{
  "type": "connected",
  "node_id": "a1b2c3d4-..."
}
```

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

## Configuration

Node system settings in Suzent configuration:

| Field | Default | Description |
|-------|---------|-------------|
| `nodes_enabled` | `true` | Enable/disable node WebSocket connections |
| `node_auth_mode` | `"open"` | Authentication mode: `open`, `approve`, or `token` |

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
