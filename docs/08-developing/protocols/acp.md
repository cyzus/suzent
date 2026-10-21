---
sidebar_position: 5
---

# ACP — Suzent in Someone Else's Editor

Suzent speaks [ACP (Agent Client Protocol)](https://agentclientprotocol.com/)
in **both directions**:

| Direction | Role | Entry point | What it means |
|---|---|---|---|
| Outbound | Suzent is the **client** | `suzent.acp.client` | Suzent drives Claude Code, Codex, … as subagents |
| Inbound | Suzent is the **agent** | `suzent acp` | Zed, enoxian, any ACP client drives *your* geist |

The outbound client is covered below; the numbered sections describe the
inbound bridge. See [a2a.md](./a2a.md) for A2A, which reaches
agents over the network; ACP is local and process-scoped — the client spawns the
agent and speaks JSON-RPC on its stdin/stdout.

## Calling an external ACP agent from Suzent

Use the existing agent tools in this order:

1. `agent_list(status="acp")` lists registered ACP configurations, including
   built-ins, with `acp_agent_id`, name, description, and `available`. This is a
   local installation check; it does not start a process, test authentication,
   or guarantee that the ACP handshake will succeed. Missing installations are
   managed in **Settings → ACP Agents**.
2. `agent(description="...", runtime="acp", acp_agent_id="<listed ID>")`
   starts a task. The default is background execution; completion wakes the
   parent. Use `run_in_background=False` to await the result. Supply `cwd` to
   select a workspace. ACP uses the external agent's tools and model: omit
   native profiles and tool lists; `model_override` is rejected. A parent with
   denied tools cannot delegate to ACP because those restrictions cannot be
   enforced on the external agent's tools.
3. `agent_send(agent_id="<returned task ID>", message="...")` continues the
   same task. For an existing accessible chat, obtain its `agent_id` from
   `agent_list(status="recent")`. Use `wait=True` for a direct reply.

| Identifier | Meaning | Used by |
|---|---|---|
| `acp_agent_id` | Registry configuration, such as `codex` | `agent` with `runtime="acp"` |
| `acp_session_id` | External ACP protocol session | Optional explicit resume through `agent` |
| `agent_id` / returned task ID | Suzent conversation or sub-agent task | `agent_send`, rather than either ACP identifier |

The inbox dispatcher routes messages for ACP chats to the ACP runtime. The
manager starts or resumes the subprocess and the client sends `session/prompt`
over stdio. Ordinary follow-ups should use `agent_send` so they retain the
Suzent task's conversation and routing.

## Outbound authentication and streaming

The outbound client implements ACP v1. Probing an agent returns its advertised
authentication methods and checks session creation. The settings login action
rechecks the handshake and calls `authenticate` only for a selected advertised
`agent` method (also the default when `type` is absent). Successful login keeps
the connection for the next session, including when credentials are scoped to
that connection; unused login connections close on backend shutdown. Login
has a five-minute deadline. Credentials remain owned by the external agent.

Authentication-required errors retain their JSON-RPC code and data. A failed
`session/load` with code `-32000` does not fall back to a new session. A prompt
authentication failure closes the live connection but preserves the saved
session ID and asks the user to sign in and retry. Suzent does not automatically
replay a task after login.

Streaming waits on updates and prompt completion directly, draining queued
updates before finishing. Frames up to 8 MiB are accepted. Each session buffers
at most 4,096 updates; overflow ends the connection with an explicit error
instead of blocking the shared RPC reader or silently dropping updates. A
later attempt reconnects. Tool updates retain their original order and fields.

See the official [authentication](https://agentclientprotocol.com/protocol/v1/authentication)
and [prompt turn](https://agentclientprotocol.com/protocol/v1/prompt-turn) contracts.

## 1. What the client gets

```sh
suzent acp
```

That command is not meant to be typed. An ACP client spawns it, keeps the pipe,
and passes its workspace as the session `cwd`:

```
client -> agent:  initialize
client -> agent:  session/new       (cwd = the client's workspace)
client -> agent:  session/prompt
agent  -> client: session/update    (message chunks, thoughts, tool calls)
agent  -> client: session/request_permission
client -> agent:  session/cancel
```

Implemented methods: `initialize`, `authenticate`, `session/new`,
`session/load`, `session/prompt`, `session/cancel`. Advertised capabilities:
`loadSession: true`, text prompts with embedded context. Images and audio are
declined at the handshake rather than silently dropped.

### Inbound authentication

`suzent acp` requires pairing by default. Initialization needs no running backend:
it advertises an agent method (`suzent-pair`) and, only when
`clientCapabilities.auth.terminal` is true, a terminal method (`suzent-terminal`).
The terminal method appends `--login --client-name <clientInfo.name>` to the
configured invocation. Exit zero means approval and credential persistence
succeeded; the editor reconnects afterward. Terminal method IDs are rejected by
`authenticate`. The agent method runs the same approval flow over `authenticate`,
printing its comparison code to stderr and reloading credentials before success.
This also supports clients using the Registry validator's older capability fields.

The local-only `/acp/auth/*` endpoints handle pending requests, approval, collection,
verification and revocation. Remote requests are refused even with a host token;
Host and Origin checks protect the browser approval surface. Requests expire in
five minutes. The CLI generates a random credential before requesting approval;
the backend stores only its SHA-256 hash. Uncollected approvals expire too.
Client credentials are keyed by backend URL and client name, protected with
Windows DPAPI or an owner-only file on POSIX. Mobile/mesh tokens are not accepted.

Each session stores the approving grant ID in `_acp_server.grant_id`. New/load,
prompt and permission continuation verify the grant; load checks ownership before
replaying history. A running turn also checks authorization once per second and
requests backend cancellation on revocation, including while the stream is silent.
This cannot undo already completed tool operations. Login after revocation creates
a different grant and cannot resume the old grant's sessions. Local processes and
`--no-require-auth` remain within Suzent's trusted-local boundary; pairing is not an
OS sandbox or a restriction on shared memory or the agent's other tools.

For Registry submission, publish a version containing this flow first, pin its
distribution in the registry manifest, and run the Registry's startup/auth checks
against that published artifact. Include the required license URL and monochrome
SVG icon, and document that a local Suzent backend and configured model are needed.
The implementation alone does not publish a package or register Suzent.

## 2. It is a translator, not a second agent

`suzent acp` runs no model. Every turn is posted to the **already-running
backend** over the loopback API and its AG-UI event stream is translated back
into ACP:

| Suzent stream event | ACP session update |
|---|---|
| `TEXT_MESSAGE_CONTENT` | `agent_message_chunk` |
| `THINKING_TEXT_MESSAGE_CONTENT` | `agent_thought_chunk` |
| `TOOL_CALL_START` / `_ARGS` / `_END` | `tool_call`, then `tool_call_update` with `rawInput` |
| `TOOL_CALL_RESULT` | `tool_call_update` (`completed`) |
| `tool_approval_request` | `session/request_permission` |
| `RUN_ERROR` | JSON-RPC error on the prompt turn |

That indirection is the point. One process owns the database, so an ACP session
is a **real chat**: it appears in the desktop UI, uses the same memory, skills,
model config, and permission rules, and survives a restart. `suzent serve` (or
`suzent start`) must be running; without it the first session fails with a
connect error rather than quietly starting a second agent stack.

An ACP session id **is** a chat id. `session/load` therefore resumes a real
conversation — and refuses any chat this surface did not create, so a client
cannot address one of your local conversations by guessing an id.

## 3. Where the files are

`session/new` binds the client's `cwd` to the session as a custom volume mounted
at `/mnt/workspace`, and pins the agent's working directory to the path the
active execution mode can actually use:

| Mode | Mount | Agent cwd |
|---|---|---|
| Sandbox | `<client cwd>:/mnt/workspace` | `/mnt/workspace` |
| Host | same mapping, resolved on the host | the real client cwd |

The binding rides along with every prompt, the same way the desktop UI sends a
chat's config on every turn, so a `session/load` that arrives with a different
`cwd` rebinds immediately. The mount is also announced in the system prompt
(host path, mount point, and whether it is a Git repo), so the model knows where
it is working.

Because edits land on the real files through a bind mount, a client that tracks
workspace changes — enoxian's proposal engine, an editor's diff view — sees them
as ordinary file writes.

## 4. Approvals stay yours

By default an ACP session runs in `default` permission mode, so a tool call that
needs approval becomes a `session/request_permission` request and the turn
blocks on the client's answer. The options offered are built from the backend's
own decision contract, so a client sees exactly the authority Suzent is willing
to grant:

| Suzent action | ACP option kind |
|---|---|
| `allow_once` | `allow_once` |
| `allow_session` / `allow_global` | `allow_always` |
| `reject` | `reject_once` |

Choosing an `allow_always` option persists the rule the label promised (a
command prefix such as `git log …`, or a whole tool), because the selected
option id is handed back to the backend as the action to resolve. A cancelled
outcome stops the turn.

To skip prompting entirely — for an unattended client — start the agent with
`--permission-mode auto` or `--permission-mode full_access`.

## 5. Flags

| Flag | Default | Purpose |
|---|---|---|
| `--server-url` | the running local backend | Bridge to a specific backend URL |
| `--permission-mode` | `default` | `default`, `auto`, or `full_access` |
| `--log-level` | `WARNING` | Diagnostics level on **stderr** |

`stdout` carries protocol traffic only. Logging is forced to stderr before
anything can write, `-v` included.

## 6. Registering with a client

**enoxian** — Suzent is a built-in agent there, so enabling it downloads
nothing; it only points the `@suzent` handle at your installed CLI. Mentions
launch it once this device's reaction policy is `push`:

```sh
enox agent install suzent
```

**Any other client** — register `suzent acp` wherever it configures external
agent servers (command `suzent`, args `["acp"]`), and it will be spawned with
the workspace as the process cwd and the session `cwd`. Check the client's own
docs for where that configuration lives.
