# Mobile wire contract, preview 1

The backend remains the source of truth. HTTP requests send `Authorization:
Bearer <host token>` and JSON bodies. Origins have no path, credentials, query or
fragment. Clients reject redirects to keep credentials bound to the selected host.

| Operation | Route | Payload/result |
| --- | --- | --- |
| List | GET /chats | `{chats: [{id,title,isRunning}]}` |
| Create | POST /chats | `{title}` → `{id,title,messages}` |
| Load | GET /chats/{id} | `{id,title,messages:[{role,content}]}` |
| Send once | POST /chat/send | `{chat_id,message}` → 202 |
| Observe | POST /chat/live | `{chat_id,wait_ms:1000,protocol:1}` → SSE or 204 |
| Stop | POST /chat/stop | `{chat_id}` |

SSE is UTF-8, blank-line-delimited, with optional comments and multiple `data:`
lines. Consume TEXT_MESSAGE_CONTENT.delta; expose RUN_ERROR.message; ignore
unknown event kinds. EOF without a terminal event does not prove task completion.
Refresh stored chat state after observing. Do not retry mutation requests.

Node uses `/ws/node` with a separate durable `device_token`, never the HTTP token.
New devices wait for desktop approval. Advertise only `device.status`, return
`{platform, foreground:true}` and reject every unknown command. Pending, connected,
ping, invoke, error are handled explicitly. Stop processing as soon as the app
leaves the foreground. Pydantic models: `src/suzent/nodes/models.py`.

Mobile uses the same [snapshot/cursor protocol](../../docs/03-developing/stream-recovery-protocol.md)
as desktop. `STREAM_SNAPSHOT` replaces transient text; `STREAM_EVENT` applies only
new consecutive sequence numbers for its transport run. Recovery sends `run_id`
and `after_seq`, with up to five attempts and bounded exponential backoff. It
never retries a send. Replaced runs request a fresh snapshot.

Only `STREAM_END` with `persisted:true` permits clearing the transient response,
and only after successfully loading saved history. Failed saves, exhausted
reconnects and history-load errors preserve received text. AG-UI completion events
and HTTP EOF are not save confirmations. Unknown nested AG-UI events are ignored
by the current text-only live view; unsupported transport frames fail recovery.

This requires a backend with protocol 1 (main after #227). It does not fall back
to the consume-once protocol. Recovery survives client reloads, not backend
restarts; no durable event journal is introduced. Structured live tool rendering
is a follow-up; persisted tool activities are rendered from chat history.
