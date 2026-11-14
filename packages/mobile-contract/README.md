# Mobile wire contract, preview 1

The backend remains the source of truth. HTTP requests send `Authorization:
Bearer <host token>` and JSON bodies. Origins have no path, credentials, query or
fragment. Clients reject redirects to keep credentials bound to the selected host.

| Operation | Route | Payload/result |
| --- | --- | --- |
| List | GET /chats | `{chats: [{id,title,isRunning}]}` |
| Create | POST /chats | `{title}` → `{id,title,messages}` |
| Load | GET /chats/{id} | `{id,title,messages:[{role,content}]}` |
| Mailbox page | POST /mobile/client/mailbox/page | `{category:"notifications" or "all",offset:0,limit:50}` → `{items,unread,hasMore}`; requires session capability `mailbox: 1` |
| Mailbox read | POST /mobile/client/mailbox/read | `{ids:[positive integer]}` or `{all:true}` → `{marked,unread}`; same visibility scope as the page |
| Scheduled tasks | GET /mobile/client/scheduled-tasks | `{tasks:[{id,name,chatId,active,isRunning,nextRunAt,lastRunAt,hasError}]}`; requires session capability `scheduled_tasks: 1` |
| Chat overview | GET /mobile/client/chats/{id}/overview | `{goal:{objective,status,turnsElapsed,maxTurns}|null, tasks:[{id,title,activeForm,status}], context:{usedTokens,limit,percent,reserveTokens,categories:[{id,tokens}]}}`; Regent adds `workQueue:[{chatId,title,projectName,state,waitingKind,waitingReason,summary}]` for waiting/running chats (blocking questions and approvals first), with empty `goal`/`tasks` and its own `context`; absent `workQueue` means an older desktop, not an empty queue; scoped like the chat; task descriptions, results and paths stay on the desktop; requires session capability `chat_overview: 1` |
| Tool media | GET /mobile/client/chats/{id}/media/{media_id} | the file's bytes, with Range support; `media_id` comes from a loaded transcript, where a finished media tool part (`generate_image`, `edit_image`, `check_video`, `speak`, `analyze_visual`, `send_file`) carries `media:[{id,kind:"image"\|"video"\|"audio"\|"file",name}]`; only `send_file` produces `file`; ids are opaque, so desktop paths never reach the phone; scoped like the chat; 404 once the file is gone; requires session capability `media: 1` |
| Surface answer | POST /mobile/client/surface-answer | `{chat_id, surface_id, answer}` → `{ok:true}`; resolves a waiting `ask_question`; needs `send`; 404 when nothing waits; requires session capability `surfaces: 1`. Ordinary surface actions are sends; see `surface-fixtures.json` |
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

### Conversation pagination (optional)

Session capability `chat_pagination: 1` enables these read-only navigation routes:

- `GET /mobile/client/navigation`: independent Regent presence plus authorized
  projects with `chatCount` (non-pinned, non-cron, non-archived chats), plus
  `running` and `unread` flags covering every authorized chat in the project, so a
  collapsed project can show activity without loading its pages. Native clients
  refresh this with each status poll.
- `POST /mobile/client/chat-page`: `{kind, value, offset, limit}` returns
  `{chats, total, nextOffset}`. Kinds are `recent`, `pinned`, `project` (value is
  project ID) and `search` (value is a title substring). Default page size is 30,
  maximum 100. Recent/project lists exclude pinned and cron entries. Search
  includes those entries and treats SQL wildcard characters literally.
- `POST /mobile/client/chat-status`: `{ids: [...]}` accepts at most 100 IDs and
  returns authorized, existing, non-archived summaries only. Omitted IDs must be
  evicted, while summaries loaded concurrently outside that request are retained.

Chat summaries carry `unreadCount`, the number of finished turns nobody has viewed
yet (absent on older desktops, read as 0). Clients show unread rows in bold, the way
the desktop sidebar does, and clear the count with `POST /mobile/client/chats/{id}/read`
when they open the conversation or while it stays on screen.

Authorization is applied before paging and counting. Regent never consumes a page
slot and still requires all-conversation access. The legacy chat index remains for
older apps; native clients fall back to it when the capability is absent.

Native clients load project pages on expansion and debounce search by 300 ms.
Load more appends with ID deduplication. Status polling updates loaded summaries
rather than reloading the index; metadata and a short recent page refresh at
60-second intervals. Explicit refresh resets pagination. Offset pages can shift
when conversations are updated remotely; refresh restarts from the newest page.

## Mobile inbox

`mailbox: 1` in `/mobile/client/session` enables the inbox. Missing capability
means the desktop must be updated; clients do not call the inbox endpoints.
Both endpoints use the existing paired-device credential and grant. An
`all_chats` grant sees all events, including notifications without a target chat.
Otherwise only events whose `target_chat_id` passes `permits_chat` are visible;
listing pagination, unread counts and read mutations all apply this scope.
Explicitly naming Regent in `chat_ids` does not bypass its all-chats requirement.
No new permission is implied by Node access, `send` or `manage_chats`.

Pages are newest-first, with a default size of 50 and a maximum of 100. `offset`
is nonnegative. `notifications` selects `route_status == "notified"`, including
read notifications; `all` includes other retained events. The response's unread
count covers the complete authorized scope, not just the page. Items contain
`id`, `source`, `eventType`, `summary`, `payload`, `status`, nullable `chatId`,
`createdAt` and nullable `readAt`. Dates include an offset. Raw routing metadata,
webhook headers and endpoint secrets are not returned. See `mailbox-fixture.json`
for the shared Swift/Kotlin decoding fixture.

Reading updates the existing `mailbox_items.read_at` used by desktop; it does
not drain background notifications. Opening the list never marks it read.
Expanding a notification marks that item read; an explicit button marks all
notifications within the device's scope, across pages. A read request must choose
nonempty positive integer `ids` (at most 100), or `all:true`, not both. Unshared,
missing or already-read ids have no effect. Empty or malformed requests return
400 rather than marking everything read. Read-only conversation grants can mark
notifications read, just as they can mark a conversation read.

Clients refresh during the existing ten-second foreground navigation poll, on
return to the foreground, on opening the inbox and on pull-to-refresh. The desktop
inbox refreshes while visible, and its sidebar retains its existing unread poll.
Read state is authoritative on the backend; failed writes display a retry message
without optimistic read changes. Changes can take one polling interval to appear
on another active client. Switching desktops clears inbox state, and stale
responses are ignored. There is no offline read queue or background push delivery.

### Shared inbox threads

Both desktop and mobile items include the same optional `presentation` object:
`threadKey`, `title`, `source`, nullable `context`, `icon` (`inbox` or `code`),
nullable `activity` and `detail`. Clients group solely by nonempty `threadKey`,
sort newest IDs first, and deduplicate IDs. Missing metadata means an independent
item; clients must not inspect signatures, provider event types, or payloads to
guess a thread. Activity codes are display semantics, not provider actions:
`created`, `closed`, `reopened`, `updated`, `edited`, `label_added`, `label_removed`,
`assigned`, `unassigned`, `review_ready`, `draft`.

The backend derives identities from source-specific adapters or the generic
source/signature fallback. Any webhook can set a nonempty string `thread_id` with
an optional `subject`, `context`, `activity`, and `detail` in its JSON body.
Thread IDs are namespaced by source; they do not change delivery rules or grants.
The API computes descriptors only after access filtering. Counts and read actions
apply only to loaded, authorized items. The shared fixtures are in
`mailbox-thread-fixtures.json`.
