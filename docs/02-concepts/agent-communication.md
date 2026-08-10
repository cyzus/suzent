# Agent Communication

Suzent treats every agent-backed conversation as an addressable session. The
stable `agent_id` is its chat ID; `kind` describes how the session originated:
`interactive`, `subagent`, `cron`, or `social`.

## Tools

| Tool | Parameters | Behavior |
|---|---|---|
| `agent` | task definition and execution options | Creates a child agent |
| `agent_list` | `status`, `limit` | Lists accessible sessions in the current project |
| `agent_read` | `agent_id` | Reads a bounded, visible transcript |
| `agent_send` | `agent_id`, `message` | Queues a durable message and wakes the target |
| `agent_stop` | `agent_id` | Cooperatively stops an active target |

The project is the authorization boundary. Hidden internal sessions (dream and
legacy wakeup chats) are not addressable. Sending to the current session is
rejected to avoid feedback loops.

## Durable Inbox

`agent_send` does not depend on an in-memory queue. It writes an
`agent_inbox_messages` row before returning. A background dispatcher uses a
database lease to claim messages and moves each row through this state machine:

```
pending -> processing -> delivered
              |
              +-> pending (retry with backoff)
              +-> failed  (attempt limit reached)
```

Message IDs are idempotency keys. Delivery also writes a hidden marker into the
target transcript. If a process exits after the target turn commits but before
the inbox acknowledgement commits, the next worker sees the marker and
acknowledges the row without running the target twice.

Sub-agent completion and failure wakeups use this inbox too, so restarting the
backend no longer discards a completed child's parent notification.

## Cron and Social Boundaries

Cron definitions and run records are already durable, but the scheduler invokes
due jobs directly. Its UI announcement deque is still an in-memory presentation
channel; it is not the agent inbox.

Social Brain also keeps a dedicated in-memory ingress queue. Raw social events
carry channel authorization, thread identity, attachments, and reply routing, so
they are validated and normalized by Social Brain before an agent turn. They are
not inserted into the generic inbox. Once normalized, their chat sessions are
visible to `agent_list` and can receive `agent_send` messages like other sessions.

This separation keeps the generic tool contract small while preserving the
special delivery semantics of Cron and social channels.

## Cross-session and Cross-device Semantics

The inbox provides real cross-session communication. It also works across
devices when those devices connect to the same Suzent backend (or backend
instances sharing the same database). Independent local installations with
separate databases do not discover or wake each other; that requires a shared
relay or synchronized database service.
