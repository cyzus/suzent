# Node Mesh — Security & Identity

Living reference for how device identity/auth works today, the threat model, and
the hardening roadmap. See [nodes.md](./nodes.md) for the user-facing feature docs.

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

## 3. Hardening roadmap

Ordered by strength / effort. Pick based on where the mesh is exposed.

### Option A — IP / host pinning (cheap, brittle)
Record the device's address at approval; reject the token from other source IPs.
- **Pro:** trivial; stops a leaked token from being replayed off-network.
- **Con:** breaks the LAN↔Tailscale flexibility (address changes invalidate the
  binding); IPs can be spoofed on a hostile L2.
- **Verdict:** not recommended as the primary control.

### Option B — TLS + fingerprint pinning (recommended for untrusted networks)
Serve `wss://`/`https://`; on pairing, record the peer's cert fingerprint and
pin it on every connection (the OpenClaw approach).
- **Pro:** stops sniffing and MITM without a full PKI; modest effort.
- **Con:** cert lifecycle (self-signed + pinned fingerprints); a TLS layer in
  front of the server.
- **Verdict:** the right next step **if** the mesh is exposed beyond a tailnet.

### Option C — public-key device identity (strongest, most work)
Each device holds a keypair; pairing exchanges public keys; connections prove
possession via a signed challenge (mTLS-style). Tokens become bound to a device
key.
- **Pro:** real device identity; tokens can't be replayed by a non-holder;
  enables per-device trust decisions.
- **Con:** most implementation + key management; **largely duplicates what
  Tailscale already provides** at the network layer.
- **Verdict:** only worth it for a first-class, transport-agnostic identity story
  independent of any VPN.

## 4. Current recommendation

- **On a tailnet:** the bearer-token + scope + revocation model is acceptable —
  Tailscale supplies the key-based identity and encryption underneath. Keep
  `node_lan_bind` off unless needed; prefer Tailscale addresses for pairing.
- **On an untrusted LAN / the internet:** do **not** rely on the current model.
  Implement **Option B (TLS + fingerprint pinning)** before exposing it.

## 5. Open items

- [ ] Decide target exposure (tailnet-only vs untrusted networks) — drives B/C.
- [ ] If B: add `wss://` support + fingerprint capture at pairing + pin on
      connect; surface the fingerprint in the Devices tab for out-of-band verify.
- [ ] Consider splitting `agent` scope (which now also covers hardware
      `peer-invoke` and the Suzent channel) into finer grants — e.g. `chat` (run
      the agent) vs `device` (drive `speaker.speak`/`camera.snap`) — if those
      should be separately consentable.
- [ ] Token rotation / expiry for `full` (host) tokens.
- [ ] Unspoofable device identity (Option C): today `node_identity` is a
      plaintext label used only for matching — a signed-challenge/keypair would
      make it an authenticator, not just an identifier.
- [ ] `list_peers` recomputes each peer's outbound status via a live `whoami`
      round-trip on every poll (~4s); cache/debounce so an open Devices tab
      doesn't fan out N requests per tick (also a mild self-DoS surface).
