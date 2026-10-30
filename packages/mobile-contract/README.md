# Mobile wire contract, preview 1

The backend remains the source of truth. HTTP requests send `Authorization:
Bearer <host token>` and JSON bodies. Origins have no path, credentials, query or
fragment. Clients reject redirects to keep credentials bound to the selected host.

| Operation | Route | Payload/result |
| --- | --- | --- |
| List | GET /chats | `{chats: [{id,title,isRunning}]}` |
| Create | POST /chats | `{title}` → `{id,title,messages}` |
| Load | GET /chats/{id} | `{id,title,messages:[{role,content}]}` |
| Scheduled tasks | GET /mobile/client/scheduled-tasks | `{tasks:[{id,name,chatId,active,isRunning,nextRunAt,lastRunAt,hasError}]}`; requires session capability `scheduled_tasks: 1` |
| Send once | POST /chat/send | `{chat_id,message}` → 202 |
| Observe | POST /chat/live | `{chat_id,wait_ms:1000,protocol:1}` → SSE or 204 |
| Stop | POST /chat/stop | `{chat_id}` |
| Attach | POST /mobile/client/upload?chat_id= | multipart `files` (≤10, ≤200 MB, Content-Length required) → `{attachments:[{id,filename,mime_type,size}]}` |

Clients show the attach control only when `GET /mobile/client/session` reports
`attachments: 1`. A send then names uploads by id, `{chat_id, message, attachments:[id]}`,
and the message may be empty when ids are present. Ids are bound to the device and
conversation that uploaded them and are kept in memory for six hours; a backend
restart expires them, and the send answers 400. User rows in a loaded transcript
carry `files:[{filename,mime_type,...}]`.

SSE is UTF-8, blank-line-delimited, with optional comments and multiple `data:`
lines. Consume TEXT_MESSAGE_CONTENT.delta; expose RUN_ERROR.message; ignore
unknown event kinds. EOF without a terminal event does not prove task completion.
Refresh stored chat state after observing. Do not retry mutation requests.

Node uses `/ws/node` with a separate durable `device_token`, never the HTTP token.
New devices wait for desktop approval. Advertise only `device.status`, return
`{platform, foreground:true}` and reject every unknown command. Pending, connected,
ping, invoke, error are handled explicitly. Stop processing as soon as the app
leaves the foreground. Pydantic models: `src/suzent/nodes/models.py`.

Mobile uses the same [snapshot/cursor protocol](../../docs/08-developing/architecture/stream-recovery-protocol.md)
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

### Regent (optional)

Updated servers prepend the singleton Regent to the chat index for `all_chats`
grants, with `platform: "focal"` and an optional
`regent: { waiting: Int, unread: Int, lastMessageAt: String | null }` object.
Its hidden system project is not exposed as a navigation group. Listing does not
initialize Regent; opening its detail does. Clients without this metadata remain
compatible. Explicit chat-ID grants do not authorize Regent's global context.
Sending/stopping/approving continue to require their respective action grants.

`POST /mobile/client/chats/{chat_id}/read` (empty JSON body) acknowledges the
conversation's unread messages using the same shared-chat authorization.
Clients use it for discovered Regent conversations on open and while visible.
Regent does not support mobile attachments, management, retry/edit or fork.

Regent delivery and reaction rendering cases are shared by both native test
suites in `regent-fixtures.json`; these transformations never change saved history.

### Activity timing (optional)

Native history presentation reads `run_timings`, `_streaming_run_id`,
`run_started_at`, `run_finished_at`, `run_active_seconds` and
`turn_last_activity_at`. Recorded active durations take precedence over wall time;
replayed run IDs are counted once and unknown waiting durations are not shown as
worked time. Missing fields remain compatible with older history. Cross-platform
cases are in `activity-timing-fixtures.json`.
