---
sidebar_position: 3
---

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
| `agent_send` | `agent_id`, `message`, `wait` | Queues a durable message and wakes the target; `wait=True` runs the target's turn now and returns its reply |
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

All local and received peer messages enter the target through the existing
system-reminder format, with sender identity and the delivery marker retained.
Native background turns use `system_reminders`; live-run injection and ACP turns
use a locally authored PUA wrapper with a `display_trigger` for the visible
transcript. Peer transport carries raw message content; the receiver owns its
wrapper and runtime nonce.

Sub-agent completion and failure wakeups use this inbox too, so restarting the
backend no longer discards a completed child's parent notification.

## Following Up With a Sub-agent

A parent continues a finished sub-agent with `agent_send`, addressing it by
task ID or chat ID. The sub-agent's chat stores its role prompt, model, memory
setting, permission mode, and the permission grants it inherited at spawn
(`followup_config`), so the follow-up turn runs as the same sub-agent rather
than falling back to the main agent's prompt, the default model, and none of
the parent's denials. A worktree that teardown keeps becomes the stored working
directory, so follow-ups edit the isolated changes, not the main checkout.

When a delivered `agent_message` came from the target's own parent, the
dispatcher queues the turn's final answer back to the parent as a
`subagent_result` (`subagent-reply-<message_id>`), which wakes it the same way
the first result did. Replies from other sessions stay in their own chat.
If queueing the reply fails, the delivery is retried; the retry finds the turn
already in the transcript, rebuilds the reply from its last answer, and queues
it under the same idempotent ID.
A message that joins a turn already in flight produces no separate reply.

`wait=True` skips the queue: the dispatcher delivers one message at a time, so a
parent waiting from inside a turn the dispatcher is running would wait on
itself. The tool runs the target turn directly and returns the reply, and the
stream layer gives the call no tool timeout, as with a blocking `agent` call.
If the wait is cancelled, the turn keeps running and a sub-agent's reply is
routed back through the inbox. Waited messages are not durable.

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

The inbox provides real cross-session communication. Paired Suzent backends are
also exposed as remote agent addresses such as `peer:4f31c02a96de`:

1. `agent_send` writes the message to the sender's durable queue with the
   `suzent_peer` transport.
2. The existing Devices grant supplies the peer URL and scoped bearer token.
3. The receiver acknowledges only after the message is committed to its own
   durable inbox.
4. The receiver wakes the authenticated peer's dedicated
   `suzent:<device_id>` session.

An offline peer is retried with bounded exponential backoff for up to 48
attempts. The sender can use `agent_read` to inspect the peer-owned session when
it comes back online, and `agent_stop` requests cooperative cancellation of that
session.

Remote callers cannot choose or inspect arbitrary local chat IDs. Optional
streaming session names are placed below their authenticated
`suzent:<device_id>:` namespace, while inbox/read/stop always operate on the
dedicated default session.
