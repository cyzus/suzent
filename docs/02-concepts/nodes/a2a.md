# A2A — Open Agent Federation

Suzent speaks [A2A (Agent2Agent)](https://a2a-protocol.org/), the open
agent-interoperability standard governed by the Linux Foundation. This is the
half of the mesh that reaches agents *we did not build* — LangGraph, ADK,
CrewAI, or anything else that implements the spec.

See [nodes.md](./nodes.md) for the device mesh and [security.md](./security.md)
for how grants and tokens work.

## 1. Where A2A sits

| Layer | Protocol | Talks to | Contract |
|---|---|---|---|
| Tools | MCP | services the agent uses | transparent |
| Devices | Suzent Nodes | your hardware | transparent capability manifest |
| Agents | **A2A** | other intelligences | **opaque execution** |

**Nodes are deliberately not A2A.** A node advertises exactly what it can do
(`camera.snap`, `system.script`) so the agent can pick a capability. A2A's model
is the opposite: you delegate a goal and never see inside. Folding nodes into
A2A would destroy the manifest that makes them useful.

The Suzent-native peer channel (`/channels/suzent/*`) also remains. It is the
trusted fast path between two Suzent installs and carries things the standard
does not: file attachments, pairing grants, mDNS discovery.

## 2. Wire format

We implement the **JSON-RPC binding**, which is what the reference SDK's
JSON-RPC client speaks and what interoperates in practice.

| Surface | Path | Auth |
|---|---|---|
| Agent Card | `GET /.well-known/agent-card.json` | **none** (public by design) |
| JSON-RPC | `POST /a2a/v1` | bearer device grant (`agent` scope) |
| Local status/UI | `/a2a/status`, `/a2a/agents`, `/a2a/outbound` | loopback or `full` scope |

Methods: `message/send`, `message/stream` (SSE), `tasks/get`, `tasks/cancel`,
`tasks/resubscribe`. Push notification configs return `-32003` (unsupported).

> **Version note.** The card advertises `protocolVersion: "0.3.0"`. A2A 1.0
> renamed methods for the *gRPC and REST* bindings (`SendMessage`,
> `/v1/message:send`); the JSON-RPC binding still uses `message/send`. Advertising
> 0.3.0 with these method names is what the official SDK's JSON-RPC client expects.

## 3. Publishing is not authorizing

The Agent Card is served unauthenticated — that is what makes discovery work —
but it is **off by default** (`CONFIG.a2a_enabled`). When off, the well-known
path 404s, so a disabled device looks like one that never spoke A2A.

Publishing announces existence. It grants nothing. `/a2a/v1` still requires the
same per-peer bearer grant that the Suzent pairing flow mints, and an
`agent`-scope token reaches only the agent surface — never `/config`,
`/nodes/devices`, or `/a2a/status`.

The card includes the device name and OS environment (e.g.
`Windows 11 (AMD64)`), so a delegating agent can judge *where* work will land.

## 4. Task lifecycle

A2A models work as a task with real states:

```
submitted → working → completed | failed | canceled
                   ↘ input-required ↗   (client answers, task resumes)
                   ↘ auth-required  ↗
```

`input-required` is the state the one-shot peer channel could not express. A
remote agent that hits an ambiguity stops and asks; the caller answers with a
normal `message/send` carrying the same `taskId`, and the task resumes.

Terminal states are final — `suzent.a2a.tasks` refuses any transition out of
them rather than silently reviving a settled task.

**Durability.** The conversation is persisted by the normal chat store (a task's
`contextId` *is* a Suzent chat id, namespaced per authenticated caller so two
remote agents cannot read each other's context). The task *wrapper* — state,
artifacts, subscribers — is in-memory and bounded; eviction never drops a task
that is still live.

## 5. Discovery

A2A defines four mechanisms: well-known URI, curated registries, direct
configuration, and authenticated extended cards. There is **no global public
registry**, and the spec has **no LAN discovery at all**.

That is why Suzent's own discovery is not redundant: mDNS and Tailscale find
peers on your network with zero configuration, which the standard cannot do.
External A2A agents are added by URL; we fetch the card to verify the address
before storing it.

## 6. Code map

| Module | Role |
|---|---|
| `suzent/a2a/types.py` | wire models (camelCase, spec-conformant) |
| `suzent/a2a/card.py` | this device's Agent Card |
| `suzent/a2a/tasks.py` | task store + state machine |
| `suzent/a2a/executor.py` | bridges a task to a `ChatProcessor` turn |
| `suzent/a2a/client.py` | outbound client (delegate to others) |
| `suzent/a2a/store.py` | registry of external agents |
| `suzent/a2a/outbound.py` | local view of delegated tasks |
| `suzent/routes/a2a_routes.py` | HTTP surface |

The wire types are hand-rolled rather than taken from `a2a-sdk` at runtime: the
SDK ships an opinionated server framework that would fight the Starlette route
style used elsewhere. Conformance is not left to trust —
`tests/a2a_protocol/test_sdk_conformance.py` drives our server with the official
SDK client, which is a **dev-only** dependency.

## 7. Known gaps

- **Push notifications** are unimplemented (`-32003`). Long-running delegation
  currently relies on streaming or polling `tasks/get`.
- **`input-required` is client-side only.** We *handle* a remote agent asking us
  a question; our own server does not yet emit that state, because a Suzent turn
  runs headless for remote callers and has no way to pause for input.
- **The Suzent peer channel is still a parallel implementation.** It should be
  rebuilt on this task engine, with attachments and grants as A2A extensions, so
  there is one lifecycle rather than two.
- **Agent Card signatures** (`AgentCardSignature`) are not produced or verified.
