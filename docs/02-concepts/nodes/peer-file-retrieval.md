# Peer File Retrieval Design

Status: **core peer-download flow implemented; host-to-peer ephemeral grants remain planned.**

This design covers how one Suzent device should retrieve files produced by
another device over the peer-control paths. The first target is
`camera.snap`, but the same mechanism should support future hardware
capabilities and agent-produced attachments.

## Problem

Peer control works for text and JSON results, but not for file bytes.

| Path | Current return shape | Where the bytes live |
|------|----------------------|----------------------|
| `suzent node invoke <peer> camera.snap` | JSON such as `{"file": "<path on peer disk>", "format": "png"}` | On the remote node host's local disk |
| `suzent nodes trigger <peer> "..."` | AG-UI/SSE text stream from the peer agent | In the remote Suzent sandbox |

The local path returned by a peer is not meaningful to the controller, and the
existing WebSocket capability protocol only JSON-serializes result objects. It
does not stream binary data.

Suzent already serves local sandbox files through `/sandbox/serve/...`, but
that route requires loopback or a `full` token. A remote peer normally holds an
`agent`-scope grant, so direct sandbox file serving is blocked by
`AGENT_ALLOWED_PATHS` in `src/suzent/auth_boundary.py`.

## Goals

- Let a controller fetch files intentionally returned by a peer capability.
- Keep the peer's existing `agent` grant narrow; do not expose arbitrary
  sandbox or host paths.
- Support large files by streaming bytes instead of embedding them in JSON.
- Preserve backward-compatible JSON capability results where practical.
- Reuse the same file reference shape for future trigger/agent attachments.
- Make file transfer direction explicit: the downloader must hold a valid token
  issued by the device serving the artifact.

## Non-goals

- General remote filesystem browsing.
- Giving `agent` tokens access to `/sandbox/serve/...`.
- Long-term file synchronization or caching.
- A cryptographic identity redesign. See [security.md](./security.md) for the
  broader auth model.

## Recommended shape

Add a peer-reachable artifact endpoint:

```text
GET /nodes/peer-files/{file_id}
```

The endpoint is reachable with an `agent`-scope token, but only for previously
registered artifacts. A capability result should return an artifact reference
instead of only returning a local path:

```json
{
  "success": true,
  "result": {
    "file": {
      "id": "pf_01HX...",
      "url": "/nodes/peer-files/pf_01HX...",
      "name": "camera-2026-07-05T11-22-33.png",
      "media_type": "image/png",
      "size": 384221,
      "expires_at": "2026-07-05T12:22:33Z"
    },
    "format": "png"
  }
}
```

The controller-side proxy, `POST /nodes/peers/{peer_id}/invoke`, may either
return the peer's relative `url` unchanged with peer metadata or normalize it
to a local proxy URL:

```json
{
  "success": true,
  "result": {
    "file": {
      "peer_id": "abc",
      "id": "pf_01HX...",
      "url": "/nodes/peers/abc/files/pf_01HX...",
      "name": "camera-2026-07-05T11-22-33.png",
      "media_type": "image/png",
      "size": 384221,
      "expires_at": "2026-07-05T12:22:33Z"
    },
    "format": "png"
  }
}
```

The local proxy URL is friendlier for the desktop UI and CLI because the
controller can fetch it from its own server; the server then fetches the peer's
`/nodes/peer-files/{file_id}` with the stored peer grant token.

## Local vs peer invoke

The artifact wrapper is only required when a file result crosses a peer
boundary.

Local node invokes can keep returning local paths:

```json
{"file": "C:\\Users\\me\\AppData\\Local\\Temp\\suzent_snap_abc.png", "format": "png"}
```

That path is meaningful to the same Suzent server and can be served or opened by
local-only code. A local agent invoking a local node does not need
`/nodes/peer-files/{file_id}` unless the result is later shared with a peer.

Peer invokes must normalize file-like results into artifact references before
responding to the remote controller. This normalization should happen at the
peer-facing server boundary, such as `peer_invoke`, or in a shared
result-normalization helper called from that boundary. Individual node handlers
should not need to know whether the caller is local or remote.

## Host-to-peer attachments

The same artifact primitive can support the host agent sending a file to a peer
agent, but the token direction and lifetime matter.

A file reference is a pull model: the receiver downloads bytes from the sender's
`/nodes/peer-files/{file_id}` route. That download is authorized by a token
issued by the sender. So if the host sends an attachment to a peer agent, the
peer must hold either an ephemeral artifact token or an already-approved
`agent`-scope token issued by the host.

That token is not guaranteed by the normal "host controls peer" setup:

| Link direction | Token holder | Token issuer | Lets holder do |
|----------------|--------------|--------------|----------------|
| Host controls peer | Host | Peer | Trigger peer agent, invoke peer capabilities, fetch peer artifacts |
| Peer controls host / reverse enabled | Peer | Host | Trigger host agent, invoke host capabilities, fetch host artifacts |

Do not require a permanent reverse grant just to send one file. A durable
reverse grant means "this peer may drive the host" and should remain an
operator-controlled relationship, not a side effect of attaching a file.

Host-to-peer attachments should use one of these policies:

1. **Mint an ephemeral artifact grant (recommended).** The host creates a
   short-lived download token scoped to one artifact or one trigger session.
   The token can only reach `GET /nodes/peer-files/{file_id}`, expires quickly
   such as after 5-15 minutes, and may optionally be single-use.
2. **Use an existing durable reverse grant.** If the operator has already
   enabled reverse control for this peer, the peer may fetch host artifacts with
   its host-issued `agent` token. This should be a trusted-link shortcut, not a
   requirement for ordinary attachments.
3. **Send text-only when no suitable grant exists.** If the peer has neither an
   ephemeral artifact grant nor a durable reverse grant, the host may still
   trigger the peer, but it must not include host artifact URLs the peer cannot
   fetch.
4. **Add a later push/upload path.** A separate endpoint could let the host push
   bytes directly to the peer while authenticating with the host's existing
   peer-issued token. That is a different trust shape and should be designed
   separately if pull-based artifact grants are not enough.

Example host-to-peer trigger payload with an ephemeral artifact grant:

```json
{
  "message": "Please inspect this image.",
  "attachments": [
    {
      "id": "pf_01HX...",
      "url": "/nodes/peer-files/pf_01HX...",
      "name": "diagram.png",
      "media_type": "image/png",
      "size": 123456,
      "expires_at": "2026-07-05T12:22:33Z",
      "download_token": "pft_..."
    }
  ]
}
```

The peer resolves the relative URL against the host base URL and fetches the
file using either the ephemeral `download_token` or, if already enabled, its
durable reverse-grant token. Raw host filesystem paths must never be sent to the
peer agent as attachments.

Ephemeral artifact grants should be separate from `DeviceTokenStore` grants.
They are not device-control credentials and should not authorize `/chat`,
`/nodes/peer-invoke`, or any route except the specific artifact download route.

## Data model

Introduce a small artifact registry on the serving device. It can start
in-memory and move to a durable JSON store only if restart survival matters.

```python
class PeerFileArtifact(BaseModel):
    file_id: str
    path: Path
    name: str
    media_type: str
    size: int
    created_at: datetime
    expires_at: datetime
    producer: str  # capability name, chat/session id, or "unknown"
```

Rules:

- `file_id` is unguessable, for example `secrets.token_urlsafe(24)` with a
  stable prefix such as `pf_`.
- `path` must be an absolute path that is registered by server-side code after
  the file is produced. The serve route must never accept raw paths from the
  request.
- `expires_at` should default to a short TTL, such as 1 hour for camera snaps.
- The registry should delete expired entries and optionally unlink temporary
  files owned by Suzent.

## Capability invoke flow

1. A controller calls its local `POST /nodes/peers/{peer_id}/invoke`.
2. The controller proxy calls the peer's `POST /nodes/peer-invoke` with the
   stored `agent` grant token.
3. The peer invokes a local node capability through `NodeManager.invoke`.
4. The peer-facing route normalizes eligible file-like results. If the result
   contains a local file path produced by a trusted built-in capability, the
   peer registers it as a `PeerFileArtifact`.
5. The peer returns a JSON-safe file reference.
6. The controller rewrites that reference to a local proxy URL:
   `/nodes/peers/{peer_id}/files/{file_id}`.
7. The UI or CLI downloads the proxy URL.
8. The controller proxy streams from
   `{peer.base_url}/nodes/peer-files/{file_id}` using the peer token.

## API additions

Serving device:

```text
GET /nodes/peer-files/{file_id}
```

Returns:

- `200` streaming response with `Content-Type`, `Content-Length` when known,
  and `Content-Disposition: attachment; filename="..."`.
- `404` when the id is unknown or expired.
- `410` is acceptable for expired artifacts if the registry distinguishes
  expired from unknown.

Controller device:

```text
GET /nodes/peers/{peer_id}/files/{file_id}
```

Returns the streamed peer file, or a JSON error if the peer is unknown, paused,
offline, forbidden, or the artifact is gone.

## Auth boundary

Add only the serving route to the peer-reachable allowlist:

```python
"/nodes/peer-files"
```

Because `scope_allows()` currently checks exact path membership, the auth layer
will need prefix support for this route, or the route should be checked before
path-param matching in a way the middleware can authorize. Prefer a small helper
such as `agent_path_allowed(path: str)` that supports exact routes and approved
prefixes.

The route should accept either:

- a normal `agent`-scope device token from `DeviceTokenStore`; or
- an ephemeral artifact token scoped to the requested `file_id`.

Ephemeral artifact tokens should be validated by the artifact registry or a
dedicated artifact-token store, not by `DeviceTokenStore`, because they do not
represent device-control grants.

Do not add `/sandbox/serve` to `AGENT_ALLOWED_PATHS`. Peer file retrieval should
only expose explicit artifacts registered for peer retrieval.

## Implementation touch points

- `src/suzent/nodes/node_host.py`
  - Keep capability handlers returning JSON-safe objects.
  - For `camera.snap`, continue saving a temp image and returning
    `{"file": path, "format": fmt}` for local compatibility.
- `src/suzent/routes/node_routes.py`
  - Add the serving route `GET /nodes/peer-files/{file_id}`.
  - Add the controller proxy route
    `GET /nodes/peers/{peer_id}/files/{file_id}`.
  - In `peer_invoke`, convert eligible local file paths to peer file references
    before returning results to a remote controller.
  - In `invoke_peer`, rewrite peer-relative file references to local proxy URLs.
- `src/suzent/auth_boundary.py`
  - Add prefix-aware allowance for `/nodes/peer-files/` under `agent` scope.
- `src/suzent/server.py`
  - Register the new routes before generic `/nodes/{node_id}` routes.
- CLI/UI
  - Render file references as downloadable attachments.
  - For `camera.snap`, optionally download the file automatically when the
    command is run from the CLI.

## Safety checks

- Register only files produced by trusted capability handlers or by known
  sandbox output collection code.
- Resolve and validate paths before serving.
- Never allow `..`, symlinks to unexpected locations, or request-provided paths.
- Apply a file size cap for artifacts that are buffered; stream everything else.
- Use conservative content types from known producers or `mimetypes`, with
  `application/octet-stream` as fallback.
- Redact local filesystem paths from peer-facing responses.
- Log artifact registration and download failures at `DEBUG` or `WARNING`, but
  do not log token values or sensitive paths.

## Agent trigger extension

The trigger path should reuse the same artifact registry once capability invoke
works.

1. Track files created during a remote agent session.
2. Register selected outputs as peer artifacts.
3. Include file references in the final chat response metadata or a side-channel
   event the controller already understands.
4. Render those references as attachments in the controller chat.

This is intentionally second because it depends on reliable session-file
attribution, while `camera.snap` has a single obvious output path.

## Rollout plan

1. Add the artifact registry and serving route on the peer.
2. Convert `camera.snap` results in `peer_invoke`.
3. Add the controller proxy route and result URL rewriting in `invoke_peer`.
4. Update auth boundary tests for exact and prefix `agent` routes.
5. Add node route tests for successful download, unknown id, expired id, paused
   peer, and forbidden sandbox access.
6. Add ephemeral artifact grants for host-to-peer attachments, with TTL and
   optional single-use semantics.
7. Allow durable reverse-grant tokens as a trusted-link shortcut, but do not
   require reverse control for one-off file attachments.
8. Update the CLI/UI rendering once the backend shape is stable.

## Alternatives considered

### Inline base64

Put bytes directly in the JSON result.

This is simple for small camera snapshots, but it bloats JSON, forces buffering,
and makes large files awkward. It is acceptable only as a temporary debug path.

### Direct sandbox URL

Return `/sandbox/serve/...` from the peer.

This reuses existing code but widens `agent` token access too much. It also ties
peer artifacts to sandbox internals and does not cover files produced by a
node-host process outside the sandbox.

### WebSocket binary frames

Extend the node WebSocket protocol to stream binary chunks.

This may be useful later for live media, but it is too much protocol work for
ordinary artifacts. HTTP streaming fits downloads better and composes with the
existing peer grant model.
