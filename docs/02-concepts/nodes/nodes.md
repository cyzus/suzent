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
  "device_token": ""
}
```

`device_token` is a durable token from a prior operator approval; when valid it
connects silently, skipping the pending/approval step.

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

## Peer control (control-grant)

For two devices that each run a full Suzent server, "drive the other's agent" is
a **control-grant** over HTTP — simpler and more robust than the WebSocket mesh
(which is for non-server companions like phones), and it streams like A2A.

- **Connect = "I want to control them."** In **Settings → Devices → Discover**,
  clicking **Control** on a peer sends it a grant request.
- **Approve = consent to be driven.** The peer's operator sees it under
  **Control requests** and approves; the peer mints a durable token and the
  controller stores it (the controller doesn't gain anything the peer didn't
  grant).
- **Trigger.** The controller sends through the peer's Suzent channel
  (below) with that token; the peer streams its agent's SSE events back. Gated by
  the [auth boundary](#auth-boundary).

### Two independent directions

A link has **two directions, tracked separately**, so each side shows only what
it owns (matched across networks by a stable per-install `node_identity`, else by
address — never by the display name, which differs per side):

- **Outbound — "I control them"** (a *status*: Ready / Revoked / Offline). Not a
  toggle — whether you can trigger a peer just reflects reachability + a valid
  grant. If the peer revoked your token, it shows **Revoked** with a
  **Re-request** action.
- **Inbound — "they control me"** (a toggle you own): whether the peer may
  trigger you. A grant you issued can be **paused** (denied at the auth boundary
  without dropping the durable token) or the whole link **removed**.

"Mutual" is not a stored mode — it is simply both directions active. **Remove**
fully severs a link: it drops the outbound peer record *and* revokes every
inbound grant issued to that machine (the reverse grant plus any grant from a
separate control-request approval, matched by address). Host tokens are
standalone full-access credentials and keep their own **Revoke**. Each grant's
row also shows lightweight usage (last-active + trigger count); rejected
unauthenticated trigger attempts are collected in a quiet, expandable list.

The bootstrap endpoints (`POST /nodes/grant-request`, `GET
/nodes/grant-status/{id}`) are the only unauthenticated surface: they issue no
secret, only queue an operator-gated request, are rate-capped + TTL'd, and the
token is served once against an unguessable `request_id`.

## Peer agents (Suzent channel)

Triggering another linked device's agent goes through the **Suzent channel**
(`POST /channels/suzent/inbound`), not a node capability. A peer you control
sends the prompt; the target runs *its own* agent (its files, memory, tools) for
your session and streams the reply back.

```bash
# From device A, drive device B's agent (B must have granted A control):
suzent nodes trigger "Device B" "summarize ~/notes"
```

On the **target**, the session behaves like any other channel conversation:

- **Persisted + resumable.** The session is a real chat keyed `suzent:<peer_id>`,
  created via the shared `ensure_channel_chat` helper (tagged `platform:"suzent"`,
  filed in the **Social** project). It shows in the chat list and **remembers
  prior turns** — re-triggering the same peer continues the same conversation
  (a fresh session only if the caller passes a new `chat_id`).
- **Live.** The turn is teed onto the target's event bus, so its UI surfaces the
  session and streams the reply in real time (and a failed turn emits a
  `RUN_ERROR`, not a silent stop).
- **Attributed.** A hidden `<system-reminder>` tells the target's agent which
  peer device triggered it (out-of-band — not part of the visible message).
- **Headless + auto-approve** — a remote peer can't answer interactive
  approvals, so a control grant runs the agent unattended.

Identity is taken from the **authenticated token**, never a body field: an
inbound call with no valid token (and no explicit `chat_id`) is rejected with
401 and creates no chat.

> `agent.run` (the old node capability) was removed — node capabilities are now
> only device hardware (`speaker.speak`, `camera.snap`). Agent-to-agent runs use
> the channel, which streams and reuses the `/chat` machinery.

## Making the server reachable

The desktop app binds the server to **localhost only** by default
(`SUZENT_HOST=127.0.0.1`), so peer devices can't reach it out of the box. To
use cross-device nodes, enable **Settings → Devices → "Reachable by other
devices"** (config `node_lan_bind`, default `false`) and **restart** the app —
the server then binds `0.0.0.0` and is reachable on its LAN/Tailscale address.

### Auth boundary (scoped tokens)

Exposing the server does **not** open the API to the network. A middleware
enforces a loopback-trusted, **scope-gated** model:

- **Loopback (the local app) is trusted** — full access, no token.
- **Remote callers** present a token (`Authorization: Bearer <token>` or
  `X-Suzent-Token`); what they can reach depends on the token's **scope**:

  | Scope | Issued by | Remote access |
  |-------|-----------|---------------|
  | `node` | WS pairing (operator approval) | WS handshake only — **no HTTP routes** |
  | `agent` | a control grant | **only** `/chat` + `/chat/stop` (trigger the agent) |
  | `full` | an explicit **host token** | the entire API (operate the device remotely) |

  A valid token outside its scope gets **403**; no/invalid token gets **401**.

- The **`/ws/node` handshake** and the **grant bootstrap** endpoints are exempt;
  they self-authenticate (the handshake by device token/approval, the bootstrap
  by an operator-approved, unguessable request id).

> Identity model and the plan to harden it (bearer tokens today, TLS/key options
> for untrusted networks) live in [security.md](./security.md).

So a granted peer can drive your agent and **nothing else** — it can't read your
config or files. To use a device fully from afar, mint a **host token**
(Settings → Devices → *Remote host access → Create host token*); it carries
`full` scope, is shown once, and is revocable like any device. This is the
deliberate, stronger credential — distinct from the scoped grant tokens.

`node_lan_bind` is therefore safe on a trusted LAN/tailnet. The bind host is
fixed once the server is listening, hence the restart.

## Discovery (LAN + Tailscale)

Suzent can find peers automatically and let you join them without typing a URL.
The two networks use **different, non-overlapping** mechanisms:

| Network | Mechanism | Notes |
|---------|-----------|-------|
| **LAN** | mDNS/Bonjour — the server advertises `_suzent-node._tcp`; peers browse for it | Same-subnet only. **Does not** traverse Tailscale (multicast isn't forwarded). |
| **Tailscale** | Enumerates online tailnet peers via the local `tailscale` CLI (`status --json`) | Works across networks; needs Tailscale installed and up. |

```bash
suzent node discover               # list LAN (mDNS) + tailnet peers
suzent node connect ws://<peer>:25314/ws/node   # join one as a node (outbound)
suzent node connections            # status + pairing code of your outbound joins
suzent node disconnect ws://<peer>:25314/ws/node
```

In the desktop app, **Settings → Devices → Discover** scans both and offers a
**Connect** button per peer. Connecting starts an outbound node host from this
device; the pairing code shows under **Joining**, and the remote operator
approves it under **Pending**.

Discovery only *locates* a gateway — it never bypasses approval. Toggle
advertising with `node_discovery_enabled` (default `true`).

> mDNS finds LAN peers; Tailscale enumeration finds tailnet peers. A device
> reachable only over Tailscale will **not** appear in the LAN list, and vice
> versa — this is expected.

## Authentication

Every new device must be **approved by an operator** before it can connect. A
device that has been approved once receives a **durable per-device token** and
reconnects silently thereafter. A new device is parked as **pending** until the
operator approves it (from the desktop app or the CLI); on approval the server
mints the durable token the node persists and reuses. Revoke a device to force
re-pairing.

This one model works for both the desktop app (approve with a click) and
headless/CLI nodes (approve with `suzent node approve <code>`), so there is no
shared secret to distribute or leak.

> ⚠️ **Plaintext transport.** `ws://` traffic is unencrypted — the durable token
> only protects you on a trusted network or over `wss://`/a tunnel. Driving a
> peer's agent is effectively authenticated remote code execution, so never
> expose the server (or a token) on an untrusted network.

### Pairing (approval + durable tokens)

```bash
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
**Settings → Devices**, a single unified list (connected nodes, peers you drive
with a direction dropdown, devices that can drive you) plus pending approvals.

## Configuration

Node system settings in Suzent configuration:

| Field | Default | Description |
|-------|---------|-------------|
| `nodes_enabled` | `true` | Enable/disable node WebSocket connections |
| `node_discovery_enabled` | `true` | Advertise over mDNS and allow LAN/Tailscale discovery |
| `node_lan_bind` | `false` | Bind `0.0.0.0` so peers can reach the server (needs restart) |

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
