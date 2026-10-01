---
sidebar_position: 3
---

# Node Mesh — Security & Identity

Reference for how device identity and auth work today, and the threat model. See [Devices & other agents](../../02-concepts/nodes.md) for the user-facing guide and [Node protocol](./node-protocol.md) for the wire protocol.

## 1. How a device is bound today

A connected device is bound by a **bearer token**, not a public key, and **not**
to an IP address.

| Concern | Mechanism | Notes |
|---------|-----------|-------|
| **Authentication** | opaque random token, `secrets.token_urlsafe(32)` | whoever presents it is authorized, from any address |
| **Identity (display)** | `display_name` ("Jessair") | UX only; not a security identity |
| **Identity (matching)** | `node_identity` — a stable per-install UUID sent in pairing | a **non-secret label** for matching/dedup across networks; spoofable, so it grants no access (auth still rides on the token). See Option C for the unspoofable version. |
| **Reachability** | `base_url` (`ip:port`) in the peer store | how to reach a peer; independent of auth |
| **Locality** | client IP, loopback check only | loopback = trusted local app; not used to pin tokens |

Stores:
- **`device_store` (`node_devices.json`)** — tokens *we issued* to others
  (devices/peers that can drive us). Record:
  `{ device_id, display_name, platform, scope, status, token_hint, callback_url,
  node_identity, approved_at, trigger_count?, last_triggered_at? }`. No key, no
  IP. `status` is `active`|`paused` (a paused grant keeps the token but is denied
  at the auth boundary); `callback_url`/`node_identity` identify the holder for
  revocation and cross-network matching.
- **`peer_store` (`node_peers.json`)** — peers *we can drive*. Record:
  `{ name, base_url, token, mode, reverse_device_id? }`. `base_url` is just the
  address to reach them; `token` is the bearer credential they issued us.

Auth boundary (`auth_boundary.py`):
- Loopback (`127.0.0.1`/`::1`/in-process) → full trust, no token.
- Remote → must present a valid token; **scope** decides which routes:
  - `node` — WS handshake only, no HTTP routes
  - `agent` — `/chat`, `/chat/stop`, `/nodes` (read-only capability list),
    `/nodes/peer-offer`, `/nodes/peer-invoke`, `/channels/suzent/inbound`,
    `/channels/suzent/whoami`
  - `full` — entire API ("use as host")
- A `paused` grant resolves to no scope (treated as invalid → denied) without
  destroying the token.
- Client IP is read **only** for the loopback decision; tokens are **not**
  IP-bound. Bootstrap endpoints (`/nodes/grant-request`, `/nodes/grant-status`,
  `/channels/suzent/grant-changed`) and the `/ws/node` handshake are exempt
  (they self-authenticate / issue no secret).

Pairing is **approve-only**: the legacy `open` (no auth) and `token` (shared
secret) connect modes were removed — every new device must be operator-approved,
which mints the durable per-device token above. Rejected unauthenticated inbound
triggers are logged (in-memory ring) for the operator to review.

## 2. Trade-offs / threat model

- **No cryptographic device identity.** There is no keypair and no
  signed-challenge proof. A leaked token is usable by anyone, from anywhere —
  the holder is not proven to be a specific device.
- **Plaintext transport.** `ws://` / `http://` expose tokens to sniffing/MITM on
  an untrusted network.
- **Mitigation in practice — Tailscale.** On a tailnet, Tailscale provides
  node-key authentication + encryption at the network layer, so the bearer token
  rides inside an already-authenticated, encrypted tunnel. This is why the
  current model is acceptable on a tailnet and **not** on an open LAN/internet.
- **Bearer tokens are revocable** (per-device, via the device store) and
  **scoped** (node/agent/full), which limits blast radius but doesn't add
  identity or transport security.

## 3. Current recommendation

- **On a tailnet:** the bearer-token + scope + revocation model is acceptable —
  Tailscale supplies the key-based identity and encryption underneath. Keep
  `node_lan_bind` off unless needed; prefer Tailscale addresses for pairing.
- **On an untrusted LAN / the internet:** do **not** rely on the current model.
  Implement **Option B (TLS + fingerprint pinning)** before exposing it.

Hardening options and open items are tracked in the [Roadmap](../roadmap.md#device-mesh-security).
