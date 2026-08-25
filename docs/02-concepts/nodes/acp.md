# ACP — Suzent in Someone Else's Editor

Suzent speaks [ACP (Agent Client Protocol)](https://agentclientprotocol.com/)
in **both directions**:

| Direction | Role | Entry point | What it means |
|---|---|---|---|
| Outbound | Suzent is the **client** | `suzent.acp.client` | Suzent drives Claude Code, Codex, … as subagents |
| Inbound | Suzent is the **agent** | `suzent acp` | Zed, enoxian, any ACP client drives *your* geist |

This page covers the inbound half. See [a2a.md](./a2a.md) for A2A, which reaches
agents over the network; ACP is local and process-scoped — the client spawns the
agent and speaks JSON-RPC on its stdin/stdout.

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

**enoxian** — register the agent, then mention `@suzent` in the circle chat
(mentions only launch anything when this device's reaction policy is `push`):

```sh
enox agent add suzent --driver acp -- suzent acp
```

**Any other client** — register `suzent acp` wherever it configures external
agent servers (command `suzent`, args `["acp"]`), and it will be spawned with
the workspace as the process cwd and the session `cwd`. Check the client's own
docs for where that configuration lives.
