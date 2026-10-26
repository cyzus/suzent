"""Memory is extracted from a chat's event log in batches, not after every turn."""

import asyncio
import json
from datetime import datetime, timezone

import pytest

from suzent.core.system_reminder import wrap_in_system_reminder
from suzent.database.chat_log import ChatEventLog
from suzent.memory import extraction_queue
from suzent.memory.extraction_queue import CURSORS_FILE, ExtractionQueue


class _RecordingMemory:
    def __init__(self, fail: bool = False) -> None:
        self.batches: list[str] = []
        self.fail = fail

    async def process_conversation_for_memories(
        self, conversation_text, chat_id, user_id, recall_query=None
    ):
        if self.fail:
            raise RuntimeError("model down")
        self.batches.append(conversation_text)

    async def process_experience(self, batch, chat_id, user_id):
        return []


class _Log:
    """Writes chat log events the way the database does, one line per event."""

    def __init__(self, root) -> None:
        self.chat_log = ChatEventLog(root)
        self.seqs: dict[str, int] = {}

    def event(self, chat_id: str, kind: str, data) -> int:
        if chat_id not in self.seqs:
            self.seqs[chat_id] = 0
            self.event(chat_id, "chat.created", {"config": {}, "messages": []})
        self.seqs[chat_id] += 1
        line = {
            "v": 1,
            "seq": self.seqs[chat_id],
            "ts": datetime.now(timezone.utc).isoformat(),
            "type": kind,
            "data": data,
        }
        path = self.chat_log.path(chat_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line) + "\n")
        return self.seqs[chat_id]

    def user(self, chat_id: str, text: str) -> int:
        return self.event(chat_id, "message.append", {"role": "user", "content": text})

    def reply(self, chat_id: str, text: str, parts=None) -> int:
        message = {"role": "assistant", "content": text}
        if parts is not None:
            message["parts"] = parts
        return self.event(chat_id, "message.append", message)

    def say(self, chat_id: str, user: str, reply: str = "ok") -> int:
        self.user(chat_id, user)
        return self.reply(chat_id, reply)


@pytest.fixture
def memory(monkeypatch):
    recorder = _RecordingMemory()
    monkeypatch.setattr("suzent.memory.lifecycle.get_memory_manager", lambda: recorder)
    return recorder


@pytest.fixture(autouse=True)
def no_legacy_transcripts(tmp_path, monkeypatch):
    monkeypatch.setattr("suzent.config.DATA_DIR", tmp_path / "data")


@pytest.fixture
def log(tmp_path):
    return _Log(tmp_path)


@pytest.fixture
async def queue(log):
    """A queue as the app has it once started: cursors already set up."""
    started = ExtractionQueue(log.chat_log)
    await started.catch_up("u1")
    return started


def _cursors(log) -> dict:
    return json.loads((log.chat_log.root / CURSORS_FILE).read_text())


def _done_through(log, chat_id: str) -> int:
    return _cursors(log).get(chat_id, [0, 0])[0]


async def test_upgrade_does_not_reextract_existing_chats(log, memory):
    """Chats from before batching were already extracted turn by turn."""
    end = log.say("old", "I live in Berlin")

    await ExtractionQueue(log.chat_log).catch_up("u1")

    assert memory.batches == []
    assert _done_through(log, "old") == end


async def test_a_few_turns_wait_for_the_chat_to_go_quiet(log, queue, memory):
    log.say("c1", "Dentist on Friday")

    await queue.note_turn("c1", "u1")

    assert memory.batches == []
    assert "c1" in queue._timers
    await queue.shutdown()


async def test_quiet_chat_is_extracted(log, queue, memory, monkeypatch):
    monkeypatch.setattr(extraction_queue, "IDLE_SECONDS", 0)
    log.say("c1", "Dentist on Friday")

    await queue.note_turn("c1", "u1")
    await queue._timers["c1"]

    (batch,) = memory.batches
    assert "USER: Dentist on Friday" in batch
    assert _done_through(log, "c1") == log.seqs["c1"]


async def test_enough_turns_are_extracted_together(log, queue, memory):
    for i in range(extraction_queue.BATCH_TURNS):
        log.say("c1", f"message {i}")
        await queue.note_turn("c1", "u1")

    (batch,) = memory.batches
    assert batch.count("### Turn on") == extraction_queue.BATCH_TURNS
    assert "c1" not in queue._timers


async def test_failed_batch_stays_queued(log, queue, memory):
    log.say("c1", "Dentist on Friday")
    memory.fail = True

    assert await queue.flush("c1", "u1") == 0
    assert _done_through(log, "c1") == 0

    memory.fail = False
    assert await queue.flush("c1", "u1") == 1
    assert "Dentist on Friday" in memory.batches[0]


async def test_batch_shows_earlier_turns_as_context_only(log, queue, memory):
    log.say("c1", "Planning a trip to Japan")
    await queue.flush("c1", "u1")
    log.say("c1", "Actually make it Korea")

    await queue.flush("c1", "u1")

    context, new = memory.batches[1].split("## New turns")
    assert "Planning a trip to Japan" in context
    assert "do not extract" in context
    assert "Actually make it Korea" in new
    assert "Japan" not in new


async def test_unfinished_turn_waits_for_its_reply(log, queue, memory):
    replied = log.say("c1", "first")
    log.user("c1", "second")

    assert await queue.flush("c1", "u1") == 1
    assert "second" not in memory.batches[0]
    assert _done_through(log, "c1") == replied


async def test_long_backlog_is_split(log, queue, memory, monkeypatch):
    monkeypatch.setattr(extraction_queue, "MAX_BATCH_CHARS", 30)
    for i in range(3):
        log.say("c1", f"message number {i}", "x" * 10)

    assert await queue.flush("c1", "u1") == 3
    assert len(memory.batches) == 3


async def test_turns_said_with_memory_off_are_skipped(log, queue, memory):
    log.say("c1", "said while memory was off")

    await queue.skip_pending("c1")
    await queue.catch_up("u1")

    assert memory.batches == []


async def test_catch_up_extracts_what_was_left_pending(log, queue, memory):
    log.say("c1", "Dentist on Friday")

    await ExtractionQueue(log.chat_log).catch_up("u1")

    assert len(memory.batches) == 1


async def test_shutdown_cancels_idle_timers(log, queue, memory):
    log.say("c1", "Dentist on Friday")
    await queue.note_turn("c1", "u1")
    timer = queue._timers["c1"]

    await queue.shutdown()

    assert timer.cancelled()
    await asyncio.sleep(0)
    assert memory.batches == []


async def test_large_tool_payloads_do_not_overflow_a_batch(log, queue, memory):
    log.user("c1", "save my notes")
    log.reply(
        "c1",
        "saved",
        parts=[
            {
                "type": "tool",
                "toolName": "write_file",
                "args": json.dumps({"content": "x" * 100_000}),
                "output": "ok",
            },
            {"type": "text", "text": "saved"},
        ],
    )

    await queue.flush("c1", "u1")

    (batch,) = memory.batches
    assert len(batch) <= extraction_queue.MAX_BATCH_CHARS


async def test_skip_waits_for_a_batch_in_flight(log, queue, memory):
    """Switching memory off mid-extraction must not let the batch rewind the cursor."""
    started, release = asyncio.Event(), asyncio.Event()
    process = memory.process_conversation_for_memories

    async def slow(*args, **kwargs):
        started.set()
        await release.wait()
        return await process(*args, **kwargs)

    memory.process_conversation_for_memories = slow
    log.say("c1", "Dentist on Friday")
    in_flight = asyncio.create_task(queue.flush("c1", "u1"))
    await started.wait()
    log.say("c1", "said while memory was off")
    skipping = asyncio.create_task(queue.skip_pending("c1"))
    await asyncio.sleep(0)

    release.set()
    await in_flight
    await skipping

    assert _done_through(log, "c1") == log.seqs["c1"]
    assert all("memory was off" not in batch for batch in memory.batches)


async def test_turn_shows_the_users_words_and_the_visible_reply(log, queue, memory):
    log.user("c1", "I moved to Lisbon" + wrap_in_system_reminder("Lives in Berlin"))
    log.reply(
        "c1",
        '<details data-reasoning="true"><summary>Thinking</summary>hmm</details>Noted.',
        parts=[
            {"type": "reasoning", "text": "hmm"},
            {
                "type": "tool",
                "toolName": "read_file",
                "args": '{"path": "notes.md"}',
                "output": "contents",
            },
            {"type": "text", "text": "Noted."},
        ],
    )

    await queue.flush("c1", "u1")

    (batch,) = memory.batches
    assert "USER: I moved to Lisbon" in batch
    assert "Berlin" not in batch
    assert "hmm" not in batch
    assert "ACTION: read_file({'path': 'notes.md'}) -> contents" in batch
    assert "ASSISTANT: Noted." in batch


async def test_scheduled_task_prompt_is_not_the_users_words(log, queue, memory):
    log.event(
        "c1",
        "message.append",
        {"role": "system_triggered", "content": "**Scheduled Task: digest**"},
    )
    log.reply("c1", "Sent the digest.")

    await queue.flush("c1", "u1")

    assert memory.batches == []
    assert _done_through(log, "c1") == log.seqs["c1"]


async def test_rewritten_history_is_not_extracted_again(log, queue, memory):
    log.say("c1", "Dentist on Friday", "Noted.")
    await queue.flush("c1", "u1")
    log.event(
        "c1",
        "messages.splice",
        {
            "start": 0,
            "delete": 2,
            "insert": [
                {"role": "user", "content": "Dentist on Friday", "timestamp": "x"},
                {"role": "assistant", "content": "Noted."},
            ],
        },
    )
    log.say("c1", "Gym on Monday")

    await queue.flush("c1", "u1")

    new = memory.batches[1].split("## New turns")[1]
    assert "Gym on Monday" in new
    assert "Dentist" not in new


async def test_retried_reply_is_extracted(log, queue, memory):
    log.say("c1", "Dentist on Friday", "first try")
    await queue.flush("c1", "u1")
    log.event(
        "c1",
        "messages.splice",
        {
            "start": 1,
            "delete": 1,
            "insert": [{"role": "assistant", "content": "retry"}],
        },
    )

    await queue.flush("c1", "u1")

    assert "retry" in memory.batches[1].split("## New turns")[1]


async def test_resumed_tool_result_is_extracted(log, queue, memory):
    tool = {"type": "tool", "toolName": "deploy", "args": {}}
    log.say("c1", "Deploy the site")
    log.event("c1", "message.append", {"role": "assistant", "parts": [tool]})
    await queue.flush("c1", "u1")
    log.event(
        "c1",
        "messages.splice",
        {
            "start": 1,
            "delete": 1,
            "insert": [
                {
                    "role": "assistant",
                    "parts": [{**tool, "output": "failed: disk full"}],
                }
            ],
        },
    )

    await queue.flush("c1", "u1")

    assert "disk full" in memory.batches[1].split("## New turns")[1]


async def test_system_chats_are_never_extracted(log, queue, memory):
    log.event("dream", "config.merge", {"set": {"platform": "dream"}, "unset": []})
    log.say("dream", "Consolidate the logs")

    await queue.catch_up("u1")
    await queue.note_turn("dream", "u1")

    assert memory.batches == []


async def test_backlog_of_the_old_transcript_queue_carries_over(log, memory, tmp_path):
    log.say("c1", "Planning a trip to Japan")
    log.say("c1", "Dentist on Friday")
    legacy = tmp_path / "data" / "transcripts"
    legacy.mkdir(parents=True)
    (legacy / "c1.jsonl").write_text(
        "\n".join(
            json.dumps({"role": role, "content": "x"})
            for role in ("user", "assistant", "user", "assistant")
        )
    )
    (legacy / "memory_cursors.json").write_text(json.dumps({"c1": 2}))

    await ExtractionQueue(log.chat_log).catch_up("u1")

    (batch,) = memory.batches
    context, new = batch.split("## New turns")
    assert "Japan" in context
    assert "Dentist on Friday" in new
