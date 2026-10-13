"""Memory is extracted from a chat's transcript in batches, not after every turn."""

import asyncio
import json

import pytest

from suzent.memory import extraction_queue
from suzent.memory.extraction_queue import CURSORS_FILE, ExtractionQueue
from suzent.session.transcript import TranscriptManager


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


@pytest.fixture
def memory(monkeypatch):
    recorder = _RecordingMemory()
    monkeypatch.setattr("suzent.memory.lifecycle.get_memory_manager", lambda: recorder)
    return recorder


@pytest.fixture
async def queue(tmp_path):
    """A queue as the app has it once started: cursors already set up."""
    started = ExtractionQueue(tmp_path)
    await started.catch_up("u1")
    return started


async def _say(tmp_path, chat_id: str, user: str, reply: str = "ok") -> None:
    transcript = TranscriptManager(str(tmp_path))
    await transcript.append_turn(chat_id, "user", user)
    await transcript.append_turn(chat_id, "assistant", reply)


def _cursors(tmp_path) -> dict:
    return json.loads((tmp_path / CURSORS_FILE).read_text())


async def test_upgrade_does_not_reextract_existing_chats(tmp_path, memory):
    """Chats from before batching were already extracted turn by turn."""
    await _say(tmp_path, "old", "I live in Berlin")

    await ExtractionQueue(tmp_path).catch_up("u1")

    assert memory.batches == []
    assert _cursors(tmp_path) == {"old": 2}


async def test_a_few_turns_wait_for_the_chat_to_go_quiet(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "Dentist on Friday")

    await queue.note_turn("c1", "u1")

    assert memory.batches == []
    assert "c1" in queue._timers
    await queue.shutdown()


async def test_quiet_chat_is_extracted(tmp_path, queue, memory, monkeypatch):
    monkeypatch.setattr(extraction_queue, "IDLE_SECONDS", 0)
    await _say(tmp_path, "c1", "Dentist on Friday")

    await queue.note_turn("c1", "u1")
    await queue._timers["c1"]

    (batch,) = memory.batches
    assert "USER: Dentist on Friday" in batch
    assert _cursors(tmp_path)["c1"] == 2


async def test_enough_turns_are_extracted_together(tmp_path, queue, memory):
    for i in range(extraction_queue.BATCH_TURNS):
        await _say(tmp_path, "c1", f"message {i}")
        await queue.note_turn("c1", "u1")

    (batch,) = memory.batches
    assert batch.count("### Turn on") == extraction_queue.BATCH_TURNS
    assert "c1" not in queue._timers


async def test_failed_batch_stays_queued(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "Dentist on Friday")
    memory.fail = True

    assert await queue.flush("c1", "u1") == 0
    assert _cursors(tmp_path).get("c1", 0) == 0

    memory.fail = False
    assert await queue.flush("c1", "u1") == 1
    assert "Dentist on Friday" in memory.batches[0]


async def test_batch_shows_earlier_turns_as_context_only(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "Planning a trip to Japan")
    await queue.flush("c1", "u1")
    await _say(tmp_path, "c1", "Actually make it Korea")

    await queue.flush("c1", "u1")

    context, new = memory.batches[1].split("## New turns")
    assert "Planning a trip to Japan" in context
    assert "do not extract" in context
    assert "Actually make it Korea" in new
    assert "Japan" not in new


async def test_unfinished_turn_waits_for_its_reply(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "first")
    await TranscriptManager(str(tmp_path)).append_turn("c1", "user", "second")

    assert await queue.flush("c1", "u1") == 1
    assert "second" not in memory.batches[0]
    assert _cursors(tmp_path)["c1"] == 2


async def test_long_backlog_is_split(tmp_path, queue, memory, monkeypatch):
    monkeypatch.setattr(extraction_queue, "MAX_BATCH_CHARS", 30)
    for i in range(3):
        await _say(tmp_path, "c1", f"message number {i}", "x" * 10)

    assert await queue.flush("c1", "u1") == 3
    assert len(memory.batches) == 3


async def test_turns_said_with_memory_off_are_skipped(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "said while memory was off")

    await queue.skip_pending("c1")
    await queue.catch_up("u1")

    assert memory.batches == []


async def test_catch_up_extracts_what_was_left_pending(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "Dentist on Friday")

    await ExtractionQueue(tmp_path).catch_up("u1")

    assert len(memory.batches) == 1


async def test_shutdown_cancels_idle_timers(tmp_path, queue, memory):
    await _say(tmp_path, "c1", "Dentist on Friday")
    await queue.note_turn("c1", "u1")
    timer = queue._timers["c1"]

    await queue.shutdown()

    assert timer.cancelled()
    await asyncio.sleep(0)
    assert memory.batches == []
