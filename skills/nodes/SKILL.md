---
name: nodes
description: Interact with companion devices (phones, laptops, headless servers) connected to Suzent.
---

## Overview

The Nodes skill lets you control remote companion devices connected to the Suzent server. Nodes connect via WebSocket and advertise capabilities (commands) you can invoke.

In **sandbox mode**, the `suzent` CLI is not available. Use the REST API via `$SUZENT_BASE_URL`.

Use this skill to:
- Discover connected devices and their capabilities
- Run commands on remote devices (take photos, run scripts, get clipboard, etc.)
- Check device connectivity status

## Sandbox API (preferred)

### Endpoints

| Action | Method | Path |
|--------|--------|------|
| List connected nodes | `GET` | `/nodes` |
| Describe node | `GET` | `/nodes/{node_id_or_name}` |
| Invoke command | `POST` | `/nodes/{node_id_or_name}/invoke` |

### Basic usage (Python)

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

## Host mode CLI (fallback)

If you are running on host and the CLI is installed, these commands are still valid:

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

## Peer agents (`agent.run`)

A node may advertise `agent.run`, which runs a prompt through *that device's
own* Suzent agent and returns its final reply — letting one agent delegate to
another linked device. Agent runs are slow, so set a generous `timeout`:

```python
result = requests.post(
    f"{base}/nodes/{node_id}/invoke",
    json={"command": "agent.run", "params": {"prompt": "summarize ~/notes"},
          "timeout": 300},
    timeout=320,
).json()
```

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

- Always list nodes first and verify capabilities before invoking.
- Prefer selecting by `display_name`, then use the resolved `node_id` for API calls.
- Keep command `params` JSON-serializable and explicit.
- Handle the case where no nodes are connected gracefully.
- Nodes require the Suzent server to be running.
