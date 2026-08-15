# Companion device protocol reference

## CLI

```text
suzent nodes list
suzent nodes status
suzent nodes describe <node_id_or_name>
suzent nodes invoke <node_id_or_name> <command> key=value
suzent nodes invoke <node_id_or_name> <command> --params '{"key": "value"}'
suzent nodes invoke <node_id_or_name> <command> --timeout 300

suzent nodes pending
suzent nodes approve <pairing_code>
suzent nodes deny <pairing_code>
suzent nodes devices
suzent nodes revoke <device_id>

suzent nodes discover
suzent nodes connect ws://<peer>:25314/ws/node
suzent nodes connections
suzent nodes disconnect ws://<peer>:25314/ws/node
```

`suzent nodes list` combines WebSocket mesh nodes, control-grant peers this device can
drive, and devices allowed to drive it.

## Local REST API

Use `$SUZENT_BASE_URL`; do not guess the server address.

| Action | Method | Path |
|---|---|---|
| List nodes | `GET` | `/nodes` |
| Describe node | `GET` | `/nodes/{node_id_or_name}` |
| Invoke node | `POST` | `/nodes/{node_id_or_name}/invoke` |
| Invoke peer | `POST` | `/nodes/peers/{peer_id}/invoke` |
| Download peer file | `GET` | `/nodes/peers/{peer_id}/files/{file_id}` |

Use `RunCommandTool` for API calls in a sandbox or host shell. A typical invoke body is:

```json
{
  "command": "camera.snap",
  "params": {"format": "png"}
}
```

Resolve names before invoking when several connections may share a display name. Prefer a
stable `node_id` or `peer_id` after resolution.

## Peer files

A peer file result has this shape:

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

Fetch `file.url` from `$SUZENT_BASE_URL`. Validate the media type and size before opening
or forwarding the file. A remote-local path is not meaningful on the controller.

## Peer agents

`suzent nodes trigger` sends a prompt through the Suzent channel. The target runs its own
agent in a persisted chat keyed to the authenticated peer, so later triggers continue that
conversation. Identity comes from the control-grant token; an unauthenticated inbound call
without an explicit authorized session is rejected.

Use `trigger` when the remote agent must decide how to complete a task. Use `invoke` when
the exact capability and parameters are already known.

## Troubleshooting order

1. Run `suzent nodes status` and `suzent nodes list`.
2. Confirm the resolved connection kind and stable ID.
3. Run `describe` and verify the exact capability name.
4. Check pairing or control-grant state.
5. Retry only after changing the identified cause; do not repeatedly invoke an offline or
   unauthorized device.
