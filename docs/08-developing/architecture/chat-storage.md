---
sidebar_position: 11
---

# Chat Storage

SQLite (`chats.db`) is the source of truth for chats. Every chat write is also
mirrored into an append-only JSONL event log, one file per chat, so the logs can
be checked against the database before they take over as the source of truth.
The remaining steps are tracked in the [roadmap](../roadmap.md#chat-storage).

## Where chats live

| Path | Contents |
|---|---|
| `<data>/chats.db` | The `chats` table: display messages, serialized agent history, config, title and lifecycle fields. Authoritative. |
| `<data>/chats/<chat_id>.jsonl` | The chat's event log. |
| `<data>/chats/.trash/` | Logs of deleted chats, renamed `<chat_id>.<utc timestamp>.jsonl`. |

The log directory is named after the database file, so a test database at
`/tmp/abc.db` keeps its logs in `/tmp/abc/`.

## Event format

Each line is one event:

```json
{"v": 1, "seq": 7, "ts": "2026-10-17T16:00:00+00:00", "type": "messages.splice", "data": {"start": 4, "delete": 0, "insert": [{"role": "assistant", "content": "..."}]}}
```

`seq` increases by one per event within a file. Folding the events in order with
`apply_event` (`src/suzent/database/chat_log.py`) yields the chat's *projection*,
the JSON form of its row that `project_chat` produces.

| `type` | `data` |
|---|---|
| `chat.created` / `chat.imported` | The whole projection. `imported` marks a chat that existed before its log. |
| `meta.set` | Changed values among `title`, `pinned`, `project_id`, `working_directory`, `created_at`, `updated_at`, `last_active_at`, `turn_count`, `context_usage`. |
| `config.merge` | `{"set": {...}, "unset": [...]}` for changed config keys. |
| `messages.splice` | `{"start", "delete", "insert"}` applied to the display messages. |
| `state.set` | Changed fields of the agent state other than its history: `kind` (`none`, `empty`, `json`, `raw`), `meta` (`version`, `model_id`, `tool_names`) and `raw` (base64, for state that is not the JSON format). |
| `history.splice` | A splice applied to the pydantic-ai message history. |
| `chat.deleted` | Empty. The file then moves to `.trash/`. |

Revision counters (`state_revision`, `finalized_revision`, `state_stage`,
`state_updated_at`) and `last_result_at` are not logged: they coordinate the
running process rather than describe the conversation. Streaming drafts
(display rows with `_streaming_draft`) are not logged either, since the turn's
real write replaces them.

## How writes reach the log

Every method on `ChatOperationsMixin` that changes a `chats` row calls
`record_chat_change(chat_id)` after its commit. That reads the committed row,
projects it, and appends the difference from the log's last projection:

- Lists are diffed by common prefix and suffix, so an appended turn is one
  small splice and a compaction or rollback is one replacement in place. The
  log grows with the conversation, not with the number of writes.
- Writes that reach the row without going through the mixin (the heartbeat
  config writes, the turn-end file snapshot) call `record_chat_change` too.
- A write the log missed is caught up by the next write to the same chat,
  because the difference is taken against the current row.
- A failure is logged as a warning and never fails the chat write.

On startup the server runs `sync_chat_logs()` in a background thread. It gives
every chat without a log a `chat.imported` event and catches up any log that
fell behind.

A crash mid-append can leave a partial final line. Readers ignore everything
after the last newline, and the next append truncates it first.

## Checking the logs

```bash
suzent chats verify
```

folds every log and compares it field by field with its row, then lists the
chats that differ. It exits with status 1 if any do.

## Turning the log off

Set `chat_store: sqlite` in the configuration, or `SUZENT_CHAT_STORE=sqlite` in
the environment. The default is `shadow`. Existing logs are left in place.
