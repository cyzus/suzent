---
name: nodes
description: Interact with companion devices (phones, laptops, headless servers) connected to Suzent.
---

## Overview

The Nodes skill lets you control remote companion devices connected to the Suzent server. Nodes connect via WebSocket and advertise capabilities (commands) you can invoke.

Prefer the `suzent nodes ...` CLI when it is available. Use the REST API via
`$SUZENT_BASE_URL` only when running in sandbox mode, writing code, or needing a
route the CLI does not expose yet.

Use this skill to:
- Discover connected devices and their capabilities
- Run commands on remote devices (take photos, run scripts, get clipboard, etc.)
- Check device connectivity status

## CLI quick start (preferred)

Use the CLI for ordinary node/peer work:

```bash
suzent nodes list
suzent nodes describe <node-or-peer-name>
suzent nodes invoke <node-or-peer-name> camera.snap format=png
suzent nodes invoke <node-or-peer-name> speaker.speak text="Hello world"
suzent nodes trigger <peer-name-or-id> "summarize ~/notes"
```

`suzent nodes list` is unified: it shows WS-mesh nodes, control-grant **peers**
this device can drive, and **devices** that can drive it. For a peer, `suzent
nodes invoke <peer> ...` automatically proxies the capability invocation to that
peer.

## Invoke vs trigger

Use **invoke** for a specific device capability. It is command-shaped,
parameterized, and returns a bounded JSON result:

```bash
suzent nodes invoke <node-or-peer-name> camera.snap format=png
suzent nodes invoke <node-or-peer-name> speaker.speak text="Hello world"
```

Use **trigger** to ask a linked peer's Suzent agent to think, plan, use tools,
and stream a conversational reply. It is prompt-shaped and continues that peer
session over time:

```bash
suzent nodes trigger <peer-name-or-id> "look at the latest logs and summarize what changed"
```

Choose `invoke` when you know the exact hardware/capability command to run.
Choose `trigger` when you want the remote agent to decide what to do, combine
multiple steps, or answer in natural language. Do not use `trigger` just to call
`camera.snap` or `speaker.speak`; use `invoke` for those.

## File results

Local node invokes may return local filesystem paths because the file lives on
the same machine. Peer invokes return downloadable file references instead of
remote-local paths:

```json
{
  "file": {
    "peer_id": "peer-id",
    "id": "pf_...",
    "url": "/nodes/peers/peer-id/files/pf_...",
    "name": "snap.png",
    "media_type": "image/png",
    "size": 12345
  }
}
```

The CLI currently prints this JSON. To retrieve the bytes from BashTool or code,
download `file.url` from the local Suzent server. Never use or expose a raw file
path returned by a remote peer; it only makes sense on that peer's disk.

## BashTool/sandbox API

### Endpoints

| Action | Method | Path |
|--------|--------|------|
| List connected nodes | `GET` | `/nodes` |
| Describe node | `GET` | `/nodes/{node_id_or_name}` |
| Invoke command | `POST` | `/nodes/{node_id_or_name}/invoke` |
| Invoke peer command | `POST` | `/nodes/peers/{peer_id}/invoke` |
| Download peer file | `GET` | `/nodes/peers/{peer_id}/files/{file_id}` |

### Basic usage (Python)

`SUZENT_BASE_URL` is injected into BashTool and sandbox executions. If it is not
set, use the CLI instead of guessing the server URL.

```python
import os
import requests

base = os.environ["SUZENT_BASE_URL"]

# 1) List nodes
nodes_resp = requests.get(f"{base}/nodes", timeout=30)
nodes_resp.raise_for_status()
nodes = nodes_resp.json().get("nodes", [])

if not nodes:
    print("No nodes connected")
else:
    # 2) Choose a node (usually by display_name)
    node = nodes[0]
    node_id = node["node_id"]

    # 3) Inspect capabilities
    detail_resp = requests.get(f"{base}/nodes/{node_id}", timeout=30)
    detail_resp.raise_for_status()
    detail = detail_resp.json()

    # 4) Invoke command
    invoke_resp = requests.post(
        f"{base}/nodes/{node_id}/invoke",
        json={"command": "camera.snap", "params": {"format": "png"}},
        timeout=60,
    )
    invoke_resp.raise_for_status()
    result = invoke_resp.json()
    print(result)

    file_ref = (result.get("result") or {}).get("file")
    if isinstance(file_ref, dict) and file_ref.get("url"):
        download_resp = requests.get(f"{base}{file_ref['url']}", timeout=60)
        download_resp.raise_for_status()
        output_name = file_ref.get("name") or f"{file_ref['id']}.bin"
        with open(output_name, "wb") as f:
            f.write(download_resp.content)
        print(f"Downloaded {output_name}")
```

### Finding a node by name

Endpoints accept either `node_id` or display name. Resolving the node first via `GET /nodes` is still recommended when names may be ambiguous:

```python
target_name = "MyPhone"
target = next((n for n in nodes if n.get("display_name") == target_name), None)
if not target:
    raise RuntimeError(f"Node not found: {target_name}")
node_id = target["node_id"]
```

## CLI reference

If you are running on host and the CLI is installed, prefer these commands:

```bash
suzent nodes list
suzent nodes status
suzent nodes describe <node_id_or_name>
suzent nodes invoke <node_id_or_name> <command> key=value [key2=value2 ...]
suzent nodes invoke <node_id_or_name> <command> --params '{"key": "value"}'
suzent nodes invoke <node_id_or_name> <command> --timeout 300   # long-running cmds

# Approve-mode pairing & durable devices
suzent nodes pending
suzent nodes approve <pairing_code>
suzent nodes deny <pairing_code>
suzent nodes devices
suzent nodes revoke <device_id>

# Discovery & joining another Suzent (outbound)
suzent nodes discover                              # LAN (mDNS) + tailnet peers
suzent nodes connect ws://<peer>:25314/ws/node     # join as a node
suzent nodes connections                           # outbound status + pairing codes
suzent nodes disconnect ws://<peer>:25314/ws/node
```

## Peer agents (Suzent channel)

Drive another linked device's agent through the **Suzent channel** — the target
runs *its own* agent for your session and streams the reply back:

```bash
suzent nodes trigger <peer-name-or-id> "summarize ~/notes"
```

Programmatically, a controller POSTs to the peer's `/channels/suzent/inbound`
with its grant token (`Authorization: Bearer <token>`) and reads the SSE reply.
The old `agent.run` node capability was removed (node capabilities are now just
device hardware like `speaker.speak`/`camera.snap`).

On the target, the peer session is a real persisted chat (keyed
`suzent:<peer_id>`, tagged `platform:"suzent"`, in the Social project): it shows
in the chat list, **remembers prior turns** (re-triggering the same peer
continues the conversation), streams live in the UI, and the agent is told which
device triggered it via a hidden system-reminder. Identity comes from the
authenticated token — an inbound call with no valid token (and no explicit
`chat_id`) is rejected 401 and creates no chat.

## Examples

```python
# Sandbox-safe invocation example
result = requests.post(
    f"{base}/nodes/{node_id}/invoke",
    json={"command": "speaker.speak", "params": {"text": "Hello world", "prompt": "cheerful"}},
    timeout=60,
).json()
```

## Best Practices

- Prefer the CLI for interactive work; use REST for BashTool/sandbox/code paths.
- Always list nodes first and verify capabilities before invoking.
- Prefer selecting by `display_name`, then use the resolved `node_id` for API calls.
- Keep command `params` JSON-serializable and explicit.
- Treat peer file `url` values as local-server download URLs.
- Handle the case where no nodes are connected gracefully.
- Nodes require the Suzent server to be running.
