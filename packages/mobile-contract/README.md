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
| Observe | POST /chat/live | `{chat_id,wait_ms:1000,replay:true}` → SSE or 204 |
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

`replay:true` requests an independent observer with retained turn history. Omitting
it preserves desktop consume-once semantics for compatibility with seeded
reconnections. Replay overflow or a slow observer yields RUN_ERROR with code
`REPLAY_UNAVAILABLE`; refresh persisted history instead of treating partial output
as a complete answer. This is not durable cursor-based replay.
