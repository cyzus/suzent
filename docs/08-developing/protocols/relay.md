---
sidebar_position: 7
title: Relay protocol
---

# Relay protocol

Suzent can be reached from outside the local network through a relay the user
deploys themselves: [suzent-relay](https://github.com/cyzus/suzent-relay), a
fork of [yetone/alma-relay](https://github.com/yetone/alma-relay). Suzent never
runs a hosted relay. This page covers the desktop side, implemented in
`src/suzent/relay/agent.py`. The relay's own description of the wire format is
[`docs/PROTOCOL.md`](https://github.com/cyzus/suzent-relay/blob/main/docs/PROTOCOL.md)
in that repository; the two must stay compatible.

## Shape

```
Suzent (RelayAgent) ──WSS /agent?th=<sha256(token)>──▶ relay ◀── HTTPS/WSS /c/<token>/… ── phone, webhook caller
```

- Suzent dials out and keeps one WebSocket per **channel**. A channel is a
  256-bit random token (`new_channel_token()`, `[A-Za-z0-9_-]{16,128}`). The
  relay only ever sees `sha256(token)` from the desktop; callers present the
  token itself in the URL.
- The first frame is `{t:'register', tokenHash, name, ver, proto: 2, key?}`.
  `key` is the relay's `RELAY_REGISTRATION_KEY` or a minted relay token.
- Protocol 2 is offered and used when the relay answers with `proto >= 2`;
  older relays fall back to protocol 1 (base64 JSON bodies).

## Serving requests

`RelayAgent` does not proxy to the local HTTP port. It calls the ASGI app in
process, building the scope from the frame, so a tunneled request is never
mistaken for a loopback client:

- `client` is `("suzent-relay", 0)`, so `AuthBoundaryMiddleware` applies the
  remote rules (token required, except the exempt prefixes such as `/hooks/`).
- The relay strips `Host`; the scope has `server: None`.
- Each channel's app is wrapped in `PathGate`, which exposes only the
  HTTP prefixes and WebSocket paths that channel is for and answers
  everything else with `404` (HTTP) or `werr` (WebSocket).

| Relay frame | Desktop handling |
| --- | --- |
| `hreq` | New `http` scope. An inline body (`b`) is delivered at once; with `stream: true` the body follows as `HBODY` binary frames and `hreqend`. |
| `HBODY` | Queued as `http.request` with `more_body`; `hack {n}` is sent when the app reads it, which paces the relay's 4 MiB window. |
| `hcancel` | Cancels the request task. |
| `wopen` | New `websocket` scope; `websocket.accept` becomes `wopened`, a close before accept becomes `werr`. |
| `wmsg` / `WTEXT` / `WBIN` | `websocket.receive`. |
| `wclose` | `websocket.disconnect`. |

Responses go back as `hres` (repeated headers such as `set-cookie` as a list),
body chunks of at most 1 MiB (`HCHUNK` binary frames in protocol 2), then
`hend`. An exception before the response starts becomes `herr`.

## Connection lifecycle

`RelayAgent.status` is a `RelayStatus` with one of these states:

| State | Meaning |
| --- | --- |
| `connecting` | Dialling or waiting to redial. `detail` says why the last attempt failed. Backoff doubles up to 60 s with jitter and resets after a successful registration. |
| `connected` | Registered; `protocol` is the negotiated version. |
| `rejected` | Close `4002`/`4003`/`4401` or an `error` frame: bad channel or key. The agent stops until reconfigured. |
| `replaced` | Close `4000`: another desktop registered the same channel. The agent stops instead of knocking it off in turn. |
| `stopped` | `stop()` was called. |

Tokens and the registration key are never logged.
