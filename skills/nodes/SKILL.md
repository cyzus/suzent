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
