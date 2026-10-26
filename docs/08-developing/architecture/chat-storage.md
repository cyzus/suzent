---
sidebar_position: 11
---

# Chat Storage

Each chat's append-only JSONL event log is its source of truth. `chats.db` is an
index of the logs: the `chats` table and its full-text search rows are what the
sidebar, search and every `get_chat` read, and they can be rebuilt from the logs
at any time. What is still planned is in the [roadmap](../roadmap.md#chat-storage).

## Display history and model context

These are separate records. The model context may be summarized or trimmed;
the visible conversation is captured from the AG-UI stream (text, reasoning,
tools, approvals, citations and inline surfaces). The run UUID identifies the
assistant record, so repeating a prompt such as “continue” does not match an
older answer. Finalization updates that run's record in place.

The quick snapshot commits the captured output and model state together, before
background post-processing. Post-processing preserves the display timeline and
does not reconstruct it from compacted model messages. Failed and stopped runs
retain whatever output was actually received; an earlier answer is not used as
a substitute. Legacy history rebuilding remains available for callers without
a captured stream identity.

During a run, transient drafts still live in SQLite rather than the JSONL log.
The completed, stopped or failed run's quick snapshot makes its captured output
durable in JSONL. An abrupt process exit before that snapshot can therefore
leave only a SQLite draft of the latest partial output.

## Where chats live

| Path | Contents |
|---|---|
| `<data>/chats/<chat_id>.jsonl` | The chat's event log. Authoritative. |
| `<data>/chats/.media/<sha256>` | Strings of 64 KiB or more from any log (pasted images, large tool output), stored once by content hash. |
| `<data>/chats/.trash/` | Logs of deleted chats, renamed `<chat_id>.<utc timestamp>.jsonl`, purged after 30 days. |
| `<data>/chats/.corrupt/` | Logs that could not be read, set aside for inspection. |
| `<data>/chats.db` | The `chats` row of each chat, its search rows, and `chat_log_index`: the `seq`, size and mtime of each log as of its last commit. |

The log directory is named after the database file, so a test database at
`/tmp/abc.db` keeps its logs in `/tmp/abc/`. File names are the percent-encoded
chat id, so a peer chat `suzent:<peer>` lives in `suzent%3A<peer>.jsonl`.

## Event format

Each line is one event. Most lines are one message, as in Codex CLI and Claude
Code transcripts:

```json
{"v": 1, "seq": 7, "ts": "2026-10-17T16:00:00+00:00", "type": "message.append", "data": {"role": "assistant", "content": "..."}}
```

`seq` increases by one per event within a file. Folding the events in order with
`apply_event` (`src/suzent/database/chat_log.py`) yields the chat's *projection*:
the JSON form of its row that `project_chat` produces, plus its retry
checkpoint, which has no row.

| `type` | `data` |
|---|---|
| `chat.created` / `chat.imported` | The projection with both lists empty; their items follow as appends. `imported` marks a chat that existed before its log. |
| `meta.set` | Changed values among `title`, `pinned`, `project_id`, `working_directory`, `created_at`, `updated_at`, `last_active_at`, `turn_count`, `context_usage`. |
| `config.merge` | `{"set": {...}, "unset": [...]}` for changed config keys. |
| `message.append` | One display message added at the end. |
| `messages.splice` | `{"start", "delete", "insert"}` applied to the display messages, for any change other than appending. |
| `state.set` | Changed fields of the agent state other than its history: `kind` (`none`, `empty`, `json`, `raw`), `meta` (`version`, `model_id`, `tool_names`) and `raw` (base64, for state that is not the JSON format). |
| `history.append` | One pydantic-ai message added at the end of the history. |
| `history.splice` | A splice applied to the history, for any change other than appending. |
| `checkpoint.set` | The retry checkpoint for the coming turn (see below). |
| `checkpoint.update` | `{"id", "set"}`: fields of that checkpoint, ignored if a newer checkpoint replaced it. |
| `chat.deleted` | Empty. The file then moves to `.trash/`. |

Anywhere in `data`, a string of 64 KiB or more is written as
`{"$media": "<sha256>"}` and read back from `.media/`.

Revision counters (`state_revision`, `finalized_revision`, `state_stage`,
`state_updated_at`) and `last_result_at` are not logged: they coordinate the
running process rather than describe the conversation, and a rebuilt row starts
them at zero. Streaming drafts (display rows with `_streaming_draft`) are not
logged either, since the turn's real write replaces them; the draft write
commits to SQLite alone.

## How a write works

Every write to a `chats` row ends in `commit_chat_changes(session, chat_ids)`
instead of `session.commit()`. That includes the methods on
`ChatOperationsMixin`, project moves, and the writes elsewhere that edit a row
directly (heartbeat config, the heartbeat route, the turn-end file snapshot).

1. The session flushes its changes to SQLite without committing, which takes
   SQLite's write lock.
2. The chat's in-process lock is taken.
3. The uncommitted row is projected and compared with the log's projection,
   which `ChatEventLog` keeps for the 64 most recent chats. Lists are diffed by
   common prefix and suffix: items added at the end become one append event
   each, and any other change (a compaction, a rollback, a retry) is one
   splice. The log grows with the conversation, not with the number of writes.
4. The events are appended and fsynced, and `chat_log_index` is updated in the
   same SQLite transaction.
5. SQLite commits. If the commit fails, the log is truncated back to its old
   size; if the process dies first, the log is ahead of SQLite.

Because the difference is taken against the row, a write that reached the row
some other way is recorded by the next logged write to that chat.

## Starting up

`ChatDatabase.__init__` runs `reconcile_chat_logs()` after the migrations and
before anything can write. It compares every log's size and mtime with
`chat_log_index` and replays only the logs that differ, so its cost is one
`stat` per chat when nothing went wrong. A replay folds the log and rewrites the
row from it when they disagree:

- events a crash kept out of SQLite are applied;
- a log ending in `chat.deleted` deletes the row and moves to `.trash/`;
- a hand-edited log is applied;
- a `chats.db` that was deleted comes back, because an empty index matches no
  log. Projects live only in `chats.db`, so a chat whose project no longer
  exists joins the default project, and the move is logged.

A crash mid-append can leave a partial final line. Readers ignore everything
after the last newline, and the next append truncates it first. A log that
cannot be read at all moves to `.corrupt/`, and the chat's next write starts a
new log from its row.

The server then runs `import_unlogged_chats()` in a background thread. It gives
every chat without a log a `chat.imported` event, and moves the checkpoints of
the old `retry_checkpoints` table into the logs before dropping it. A chat
written before the import reaches it gets its `chat.imported` from that write.

## Retry checkpoints

`save_retry_checkpoint` runs at the start of a turn. When the state it is given
is the chat as stored, which is the normal case, the checkpoint's `before` is
`{"seq": n}`: the position of the event just before it. Only a checkpoint that
differs from the stored chat carries a copy of the messages and state. A retry
folds the log up to `n` to get the state it restores, then writes that state as
an ordinary rewrite, so the log keeps every turn that was retried away.

## Commands

```bash
suzent chats show <chat_id>  # print the conversation the log holds
suzent chats verify          # fold every log, compare it with its row, exit 1 on any difference
suzent chats rebuild-index   # rewrite every row from its log; stop the server first
```

## Compaction failure and concurrency

Compaction rewrites the model context, while streamed display rows remain the
conversation timeline. An empty summary, an incomplete chunk, or a timeout must
not replace context with a placeholder or discard the unsummarized middle.
Automatic compaction keeps the input history on failure; when the estimated
request already fills the context window it raises an error instead of sending
that request. Summaries that do not reduce the history's estimated token count
are skipped. Token estimates are approximate and do not guarantee provider
acceptance.

The retained tail begins at a safe tool-call boundary. The latest real user
prompt is also retained when it falls outside that tail, including its image or
file parts. Summary requests distinguish user text from tool results. Chunk
summaries are limited to three concurrent calls, and every chunk must succeed
before a merged summary can replace context.

Manual `/compact` uses the configured compaction timeout and commits against the
revision read before summarization. If a newer snapshot has committed meanwhile,
it reports a skipped result and preserves that newer state. Complete, skipped,
and error events terminate the frontend's compaction indicator.

[Pydantic AI Harness compaction](https://pydantic.dev/docs/ai/harness/compaction/)
provides reusable model-context strategies, including incremental summarization,
user-message retention and tool-pair preservation. Suzent currently uses its own
history processor; those strategies do not replace its display log or revision
checks. The installed Harness 0.24.0 differs from the current online API (for
example, it lacks `compact_now`), so adopting it requires a version-specific
integration and regression tests.
