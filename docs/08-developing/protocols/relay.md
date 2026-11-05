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

## Settings and channels

`RelayService` (`src/suzent/relay/service.py`) is created in the server
lifespan as `app.state.relay` and owns the user's relay settings:

- `relay.json` in the user config directory holds `{url, enabled}`.
- The registration key and the channel tokens live in the secret store under
  `SUZENT_RELAY::*`, a private prefix that is never exported to the
  environment.
- The **webhook channel** is one `RelayAgent` behind
  `PathGate(http_prefixes=("/hooks/",))`. Its public URL for a webhook is
  `<relay>/c/<channel token>/hooks/<webhook token>`; the cron routes return it
  as `webhook_relay_url` next to `webhook_path` whenever they mint a webhook.
- Resetting deletes the channel tokens, so new ones are minted and every old
  relay URL stops resolving.

Operator routes (host authorization, like the rest of `/mobile/` outside
`/mobile/client/`):

| Route | Purpose |
| --- | --- |
| `GET /mobile/relay` | `{url, enabled, has_key, state, detail, protocol}`. The key itself is never returned. |
| `POST /mobile/relay` | `{url, key?, enabled}`. `key` omitted or `null` keeps the stored key, `""` removes it. `400` for a URL that isn't http(s). |
| `POST /mobile/relay/reset` | New channel tokens. |

## Phones: end-to-end encryption

Phones use a second channel, the **phone channel**, whose relay can see only
ciphertext. Its agent serves `E2EEndpoint` (`src/suzent/relay/e2e.py`), which
answers every plaintext `hreq` with `403` and every WebSocket except
`/__suzent_e2e__` with `werr`: those could only have come from the relay.

The pairing QR code (and `GET /mobile/client/session` for phones paired
earlier) carries

```json
{"relay": {"version": 1, "url": "https://relay.example", "channel": "<phone channel token>", "key": "<base64url P-256 public key>"}}
```

`key` is the desktop's static relay key, `relay_identity.pem` in the user
config directory. It is separate from the mobile TLS CA key and survives a
channel reset.

### Handshake (`suzent-e2e/1`)

A Noise-NK-style exchange over P-256, chosen because Android's minimum SDK
lacks X25519 and both CryptoKit and `javax.crypto` have P-256, HKDF and
AES-GCM.

1. The phone opens `wss://<relay>/c/<channel>/__suzent_e2e__` and sends its
   ephemeral public key `e` (65 bytes, uncompressed X9.62) as one binary message.
2. The desktop picks an ephemeral `e'` and replies with `e' || tag` (65 + 16
   bytes).

Both sides compute:

```
th   = SHA-256("suzent-e2e/1" || SHA-256(channel token) || S || e || e')
okm  = HKDF-SHA256(ikm = ECDH(e, S) || ECDH(e, e'), salt = th, info = "suzent-e2e/1 keys", L = 96)
confirm, phone_to_desktop, desktop_to_phone = okm[0:32], okm[32:64], okm[64:96]
tag  = AES-256-GCM(confirm, nonce = 0, plaintext = "", aad = th)
```

The phone checks `tag`; only the holder of the static key can produce it. The
phone itself is not authenticated by the handshake: it proves who it is with
its mobile bearer token inside the channel, exactly as on the LAN gateway.

### Messages

Every later WebSocket message is binary: `AES-256-GCM(key for the direction,
nonce = 4 zero bytes || u64 big-endian counter, aad = none)`. Each direction's
counter starts at 0 and goes up by one per message, so a replayed, dropped or
reordered message fails and the desktop closes the socket (`1008`).

The plaintext is one relay frame: `0x00` followed by a JSON frame, or `0x01`
followed by a binary frame. The phone plays the relay's part (`hreq`, `HBODY`,
`wopen`, ...) and the desktop answers through the same `_Tunnel` code that
serves the relay socket, with the app wrapped in `MobileGateway`. A phone over
the relay therefore reaches exactly the paths the LAN mobile gateway allows,
with `client = ("mobile-gateway", 0)`.

`tests/relay/e2e_vectors.json` fixes every value of one handshake and four
messages from fixed private keys. The mobile apps test against the same file.
