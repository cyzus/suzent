# Migration Plan — Agent-to-Agent Triggering → a Suzent Channel

Status: proposed. Experimental PR — **no backward-compat constraints**; we can
delete the duplicate path outright. See [nodes.md](./nodes.md) and
[security-plan.md](./security-plan.md).

## 1. Problem

Agent-to-agent triggering was built as a parallel **control-grant** subsystem
that re-implements things the **channels / SocialBrain** stack already does:

| Concern | control-grant (now) | channels / SocialBrain (existing) |
|---------|---------------------|-----------------------------------|
| pairing/consent | `grant-request` → operator approve → token | `_handle_handshake` → token → `approve_by_token` |
| who's allowed | device tokens in `device_store` | per-sender **allowlist** |
| run the agent on an inbound message | bespoke `/chat` call | `SocialBrain._handle_message` |
| stream the reply | SSE passthrough in `trigger_peer` | `ChannelManager.send_stream` |
| sessions per counterpart | peer_id | `UnifiedMessage.get_chat_id()` = `platform:sender_id` |

A remote Suzent is just **another contact**. Agent messaging belongs behind
channels; only **capability RPC** (camera/speaker) and **transport/discovery**
belong to the node mesh.

## 2. Target architecture

Two clean layers, one pairing:

```
A (controller)                         B (target)
  └─ SuzentChannel.send ──HTTP/SSE──▶  POST /channels/suzent/inbound
                                         └─ ChannelManager → SocialBrain
                                              └─ agent turn → stream reply ◀──┘

Capability RPC (camera/speaker) stays:  A ──HTTP token──▶ B /nodes/peer-invoke
```

- **Agent ↔ agent** = a **`SuzentChannel`** driver (`platform="suzent"`). Inbound
  peer messages flow through `ChannelManager` → `SocialBrain` (auth, sessions,
  steer/queue, agent run, streamed reply). Outbound = HTTP POST to the peer's
  inbound endpoint, reply streamed back.
- **Capability RPC** (`speaker.speak`, `camera.snap`) = node mesh `peer-invoke`,
  unchanged. It is request/result, not a chat turn — does **not** become a
  channel.
- **One pairing** establishes a linked peer and yields *both*: a transport token
  (auth boundary) **and** a SuzentChannel contact entry (allowlist).

## 3. The `SuzentChannel` driver

`src/suzent/channels/suzent.py`, a `SocialChannel`:

- `connect()` — register the peer contact store; no outbound polling.
- `send_message(target_id, content)` — `POST {peer.base_url}/channels/suzent/inbound`
  with the grant token; for streaming, read the SSE reply.
- inbound route `POST /channels/suzent/inbound` (auth-boundary, agent scope):
  build a `UnifiedMessage(platform="suzent", sender_id=<peer id>, content=…)`,
  call `on_message` → `ChannelManager.handle_incoming_message`, and **stream the
  agent's AG-UI events back on the same response**.
- `supports_streaming = True` (new) so the reply is true SSE passthrough, not
  `send_stream`'s accumulate-then-send.

Contacts (name, base_url, token, mode) live in the channel's store — i.e.
`peer_store` is **repurposed** as the SuzentChannel contact store, not a separate
concept.

## 4. Auth / pairing unification (the central decision)

Collapse the two pairing flows into **one**, with two distinct checks:

1. **Transport** (can you reach the HTTP surface at all) — the existing
   **auth boundary**: bearer token, `agent` scope now also covers
   `/channels/suzent/inbound`. Loopback stays trusted.
2. **Application** (is this peer an approved agent contact) — the **social
   allowlist**: `sender_id` (= peer id) must be approved.

**One pairing flow** produces both: on approve, mint the transport token **and**
add the peer to the suzent allowlist + contact store. Reuse `SocialBrain`'s
token handshake, but add a **programmatic (non-chatty) mode**: no human greeting,
a structured `pair` request → operator approves in the Devices tab → token +
allowlist entry returned. Delete the separate `grant-request`/`grant-status`/
`grants/*` endpoints; the social pairing (made programmatic) is the single path.

## 5. Streaming

`SocialBrain` today accumulates and sends one message. Add a streaming path used
by `SuzentChannel`: the inbound route runs the turn and forwards AG-UI events
(`TEXT_MESSAGE_CONTENT`, tool calls, `RUN_FINISHED`) to the open response as SSE.
Implement as a per-request sink the brain writes to, or a `stream=True` branch in
`_handle_message`. (This also benefits real social channels that can stream.)

## 6. What stays vs. what's deleted

**Stays:**
- WS node mesh (`/ws/node`, companions) + `peer-invoke` capability RPC.
- Discovery (mDNS/Tailscale), `device_store` (transport tokens + scopes),
  `auth_boundary`, `node_lan_bind`.
- `peer_store` — repurposed as the SuzentChannel contact store.

**Deleted (no legacy to keep):**
- `POST /nodes/control`, `GET /nodes/control-status` (controller-side grant).
- `POST /nodes/grant-request`, `GET /nodes/grant-status/{id}`,
  `GET /nodes/grants`, `grants/{id}/approve|deny` — replaced by unified pairing.
- `POST /nodes/peers/{id}/trigger` and `nodes.trigger` client/CLI — agent runs
  now go through the SuzentChannel send path.
- The duplicate grant registry in `NodeManager` (`_grant_requests`, etc.).

**Kept but moved:** `peer-offer`/mutual → a "reverse contact" in the channel
(A and B each have the other as a suzent contact).

## 7. Migration phases

1. **Add `SuzentChannel`** + inbound route + streaming reply; wire to
   `ChannelManager`/`SocialBrain`. (Agent triggering works through it.)
2. **Unify pairing** — one programmatic handshake that yields token + allowlist +
   contact; point the Devices tab "approve/deny" at it.
3. **Repoint trigger** — UI/CLI "trigger a peer" sends via the SuzentChannel.
4. **Delete** the control-grant agent-trigger endpoints + grant registry (§6).
5. **Docs** — fold peer-agent docs into the channels concept; node docs keep only
   mesh + capability RPC + discovery.

## 8. Frontend impact

Devices tab mostly unchanged: "Control / Mutual / Paused" stays, but the row's
trigger action and pairing call the channel/unified-pairing endpoints. "Control
requests" → the unified pairing approvals. WS-node rows and capability invoke are
unaffected.

## 9. Tests

- `SuzentChannel` round-trip: inbound message → agent turn → streamed reply.
- Unified pairing: pair → token minted + allowlist entry + contact stored;
  deny path; unauthorized peer rejected by allowlist (not just transport).
- Capability RPC (`peer-invoke`) still works against the repurposed contact store.
- Auth boundary: `agent` scope reaches `/channels/suzent/inbound`, not config.

## 10. Decisions (resolved)

- [x] **Contact identity = peer id.** `sender_id` is the stable contact/device id
      minted at pairing (one per side); name is display only, address is
      reachability only. Chat session = `suzent:<peer_id>`.
- [x] **Two independent contacts.** Each side owns its contact + token; "mutual"
      is derived ("I have them AND they have me"). **Added requirement:** when A
      revokes B or changes B's scope, **B must be notified** — propagate the
      change (B self-verifies on receipt; see §2b below).
- [x] **`agent.run` fully subsumed.** Drop it as a node capability; agent
      triggering goes only through the SuzentChannel. Node capabilities stay for
      hardware (`speaker.speak`, `camera.snap`).
- [x] **Start inline.** The SuzentChannel inbound route runs the turn directly and
      streams (reusing the `/chat` path); SocialBrain is used for auth/allowlist/
      session bookkeeping. Upgrade to a streaming sink only if steer/queue is
      needed for peer sessions.

## 2b. Revocation / scope-change propagation

Two independent contacts means a grantor must tell the grantee when access
changes. When the grantor (B) revokes or re-scopes the holder (A):

1. B records A's callback base_url at pairing.
2. On revoke/scope change, B sends a best-effort
   `POST {A}/channels/suzent/grant-changed { status: revoked|rescoped, scope? }`.
3. The notice is a **hint, not trusted**: on receipt A re-verifies by making a
   real authenticated call back to B; if it now 401/403s (or returns the new
   scope), A updates its contact record + UI. This avoids needing strong auth on
   the callback (a spoofed notice just makes A double-check and find nothing
   changed).
