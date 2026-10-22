---
sidebar_position: 10
title: Roadmap & known gaps
description: Planned work and known gaps, collected in one place so the architecture pages describe only what exists today.
---

# Roadmap & known gaps

The architecture and protocol pages describe Suzent as it works today. Planned
work and known gaps live here instead, so readers can tell the two apart. When
an item ships, move its description into the relevant page and delete it here.

## ACP integration

The settings page supports protocol-driven authentication for outbound agents.
Inbound editor pairing already supports terminal and agent authentication.
Remaining outbound work:

- Capability-gated logout.
- Byte-budgeted streaming buffers and measured frontend render batching. The
  current event-count limit fails explicitly on overflow; it is not disk-backed
  replay or transparent recovery of an interrupted turn.

## Mobile apps

See [Native mobile clients](./architecture/mobile.md) for what exists today.

Planned, in order:

1. **Interactive tools and attachments** — scoped upload. (Mobile tool approvals
   have shipped; see [Native mobile clients](./architecture/mobile.md#mobile-tool-approvals-and-activity-rail).)
2. **Device capabilities** — user-confirmed camera capture and upload, audio capture,
   single location fix; native permission and lifecycle adapters.
3. **Resilience** — durable event cursor/replay, idempotent send IDs in the backend, local
   outbox and transcript cache, endpoint migration, retry/backoff, device command
   deadlines and deduplication. Current sends are never retried automatically.
4. **System integration** — share extensions/intents, opt-in APNs/FCM notification
   delivery, platform-specific background work, accessibility and device QA.

## Plugins

See [Plugins](./architecture/plugins.md) for what exists today: tools, slash
commands and skills.

Planned, in order:

1. **Lifecycle hooks** — `ctx.register_hook()` for session start and end,
   before and after each model call, and before and after each tool call (with
   the option to block a call). The goal-turn accounting in
   `tools/plan_hooks.py` and the skill catalog reminder in `skills/hooks.py`
   would move onto these hooks as built-in plugins.
2. **Chat apps as plugins** — `ctx.register_channel()` feeding
   `ChannelManager`, whose `driver_map` is fixed today, so new chat apps can
   ship outside this repository.
3. **Providers as plugins** — model, image, video and speech providers.
4. **Settings UI** — a Plugins page to list, enable and disable plugins and see
   load errors, instead of only the CLI.
5. **Declared capabilities** — a manifest list of what a plugin needs
   (network, shell, sending messages) that the user grants when enabling it.

## Chat storage

See [Chat storage](./architecture/chat-storage.md) for what exists today: each
chat's JSONL log is authoritative and `chats.db` is rebuilt from the logs.

Not done yet:

- **Memory-extraction transcripts** (`transcripts/*.jsonl`) are still written
  separately. They double as the extraction queue, with per-chat cursors, so
  deriving them from the chat log means moving those cursors onto log `seq`s.
- **Media and log compaction.** Nothing removes `.media/` files once no log
  refers to them, and a log never shrinks: compaction and rollbacks keep the
  replaced turns in earlier lines. A `suzent chats compact-log` would rewrite a
  log as one `chat.imported` snapshot plus the events after its retry
  checkpoint.
- **Ideas from pydantic-ai-harness `StepPersistence`** not yet taken: a
  tool-effect ledger (`tool.started` / `tool.finished`) so a restart can tell
  which tool calls may already have run, and marking saved history as complete
  or interrupted so an interrupted history is repaired before it is replayed.
- **System chats.** Dream and sub-agent chats still keep no agent history.
  Logging it, with an explicit `run.reset` event where dream deliberately
  starts over, would let a sub-agent woken by `agent_send` keep its context.

## A2A

See [A2A](./protocols/a2a.md) for what exists today.

- **Push notifications** are unimplemented (`-32003`). Long-running delegation
  currently relies on streaming or polling `tasks/get`.
- **`input-required` is client-side only.** We *handle* a remote agent asking us
  a question; our own server does not yet emit that state, because a Suzent turn
  runs headless for remote callers and has no way to pause for input.
- **The Suzent peer channel is still a parallel implementation.** It should be
  rebuilt on this task engine, with attachments and grants as A2A extensions, so
  there is one lifecycle rather than two.
- **Agent Card signatures** (`AgentCardSignature`) are not produced or verified.

## Device mesh security

See [Node security](./protocols/node-security.md) for how device identity and
auth work today, and its current recommendation.

### Hardening options

Ordered by strength / effort. Pick based on where the mesh is exposed.

#### Option A — IP / host pinning (cheap, brittle)
Record the device's address at approval; reject the token from other source IPs.
- **Pro:** trivial; stops a leaked token from being replayed off-network.
- **Con:** breaks the LAN↔Tailscale flexibility (address changes invalidate the
  binding); IPs can be spoofed on a hostile L2.
- **Verdict:** not recommended as the primary control.

#### Option B — TLS + fingerprint pinning (recommended for untrusted networks)
Serve `wss://`/`https://`; on pairing, record the peer's cert fingerprint and
pin it on every connection (the OpenClaw approach).
- **Pro:** stops sniffing and MITM without a full PKI; modest effort.
- **Con:** cert lifecycle (self-signed + pinned fingerprints); a TLS layer in
  front of the server.
- **Verdict:** the right next step **if** the mesh is exposed beyond a tailnet.

#### Option C — public-key device identity (strongest, most work)
Each device holds a keypair; pairing exchanges public keys; connections prove
possession via a signed challenge (mTLS-style). Tokens become bound to a device
key.
- **Pro:** real device identity; tokens can't be replayed by a non-holder;
  enables per-device trust decisions.
- **Con:** most implementation + key management; **largely duplicates what
  Tailscale already provides** at the network layer.
- **Verdict:** only worth it for a first-class, transport-agnostic identity story
  independent of any VPN.

### Open items

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
