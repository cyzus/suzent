# Stream recovery protocol

Desktop chat sends, retry/edit, steering, approval resume, heartbeat and Canvas
turns can recover their in-progress output after a page reload or connection
loss. Native and ACP producers share the same transport. The backend owns the
snapshot; browser sessionStorage is only an optional visual seed.

## Requests and frames

Start a queued turn using the existing `/chat/send` or `/chat/steer-send` endpoint,
then POST `/chat/live`:

```json
{"chat_id":"chat-id","protocol":1,"wait_ms":0}
```

For a direct `/chat` request, add `"protocol":1`. The response uses the same
frames and its producer continues when the HTTP observer disconnects. Recovery
always uses `/chat/live`, never repeats the original send.

The initial SSE frame contains an authoritative snapshot:

```json
{"type":"STREAM_SNAPSHOT","run_id":"transport-run-id","seq":42,"events":[]}
```

`events` contains the current run's AG-UI events, compacting adjacent text,
reasoning and tool-argument deltas. This deliberately reuses the frontend's
existing reducer for Native and ACP custom events instead of introducing a
second renderer-specific projection. Replace transient parts and reduce these
events from an empty state. Previously completed turns remain in chat history.
The transport run ID is distinct from provider/agent run IDs.

Subsequent frames contain one event and a monotonically increasing sequence:

```json
{"type":"STREAM_EVENT","run_id":"transport-run-id","seq":43,"event":{"type":"TEXT_MESSAGE_CONTENT","messageId":"m","delta":"hello"}}
```

Reconnect with `run_id` and `after_seq`, the last applied sequence. Duplicate
sequences are ignored. An unknown run, future cursor or expired replay window
receives a replacement snapshot. Snapshot capture and subscription handoff occur
on the same event loop without yielding; serialization may run on a worker.
Events arriving during serialization are delivered after the snapshot cursor.
Slow observers reset from a snapshot instead of silently losing an event suffix.
Observers never compete for a consume-once queue.

Only the explicit terminal frame completes the transport:

```json
{"type":"STREAM_END","run_id":"transport-run-id","seq":43,"persisted":true,"superseded":false}
```

Native streams wait for their own post-processing task's display/state commit;
ACP already writes its response before its producer exits. A failed save sets
`persisted:false`; it must not be presented as a successful save. Stale native
revision finalizations are recorded as skipped, not successful writes. A replaced
run sets `superseded:true`; the observer reconnects to the replacement run.
`RUN_FINISHED`/`AGENT_FINISHED` inside the event stream do not mean the final
display commit has completed. Neither does an unexpected HTTP EOF.

The desktop retains its transient response through the committed-history load,
without appending a duplicate optimistic assistant message. Confirmed paths no
longer use the fixed 800 ms delay. ACP approval resolutions and answered inline
forms are included in the event history so replay does not reopen their actions.

An idle probe returns 204. A fresh probe of a completed, successfully saved run
also returns 204 and the UI reloads history. Reconnects with a cursor can drain
retained terminal events. A dropped event-bus subscriber receives an EOF so
EventSource reconnects and refreshes its active-stream snapshot.

## Retention and limits

- The delta replay window retains 4,096 events per run. The compact full snapshot
  is independent of that window and grows with the current run's output.
- Adjacent deltas accumulate as fragments; full strings are joined only at an
  event boundary or snapshot read, avoiding quadratic per-token copying.
- Completed runs are retained for up to five minutes and capped at 64 chats.
  Cleanup is lazy on registry reads/registration. Active producers and pending
  saves are not evicted. Existing connected observers keep their queue reference.
- Recovery state is in the backend process. This supports browser reloads,
  chat switches, multiple observers and transient network loss. It does **not**
  introduce a durable event journal or resume an agent after a backend restart.
  After restart, persisted chat state remains the fallback.
- Recovery retries use capped exponential backoff with five attempts after lost
  progress. Failed recovery preserves the received response and shows a localized
  error. This is not send idempotency: no automatic send retry is performed.
- Existing clients omitting `protocol` retain their legacy wire format. The
  separate mobile preview PR must opt into this protocol before dropping its
  older replay implementation. Legacy multipart clients retain their old path.

## Validation

Tests cover snapshot-to-live handoff, independently consuming observers, replay
window overflow, invalid cursors, fragmented UTF-8 SSE, lost acknowledgements,
unexpected EOF, duplicate deltas, replacement runs, save failure/cancellation,
ACP approval resolution and resolved inline forms. Route tests disconnect a
real response observer while a deterministic Native/ACP-shaped producer keeps
running, then recover its prefix and suffix through `/chat/live`. These tests
use isolated data and do not make paid model calls or modify real conversations.

A synthetic transport check on the development Mac appended 10,000 one-KiB
text deltas (9.77 MiB) in 38.74 ms total, captured the compact snapshot in 0.96 ms,
and retained one snapshot event plus 4,096 tail events. This measures the replay
accumulator only; it excludes model latency, networking and browser rendering.
