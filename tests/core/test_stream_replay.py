import asyncio
import json

import pytest

from suzent.core.stream_replay import StreamReplay
from suzent.core.stream_registry import _BusStreamQueue


def chunk(kind: str = "TEXT_MESSAGE_CONTENT", **values: object) -> str:
    return f"data: {json.dumps({'type': kind, **values})}\n\n"


def decode(frame: str) -> dict:
    return json.loads(frame.removeprefix("data: "))


def test_snapshot_survives_legacy_consumption_and_tail_eviction():
    queue = _BusStreamQueue("chat", maxsize=2)
    for i in range(100):
        queue.put_nowait(chunk(messageId="m", delta=str(i), timestamp=i))
        queue.get_nowait()
    snapshot = queue.replay.read(None, None)[0]
    assert snapshot["seq"] == 100
    assert len(snapshot["events"]) == 1
    assert snapshot["events"][0]["delta"] == "".join(map(str, range(100)))
    assert len(queue.replay.tail) == 2
    assert queue.replay.read(queue.replay.run_id, 1)[0]["type"] == "STREAM_SNAPSHOT"


def test_cursors_and_unknown_runtime_events_are_preserved():
    replay = StreamReplay()
    replay.append(chunk(messageId="m", delta="a"))
    replay.append(
        chunk("CUSTOM", name="acp.permission_request", value={"id": "approval"})
    )
    replay.append(chunk(messageId="m", delta="b"))
    snapshot = replay.read(None, None)[0]
    assert len(snapshot["events"]) == 3
    assert replay.read(replay.run_id, 2)[0]["event"]["delta"] == "b"
    assert replay.read(replay.run_id, 3) == []
    for run_id, seq in [("old-run", 3), (replay.run_id, 999), (None, None)]:
        assert replay.read(run_id, seq)[0]["type"] == "STREAM_SNAPSHOT"


async def test_snapshot_handoff_has_no_gap_and_two_observers_do_not_compete():
    replay = StreamReplay()
    replay.append(chunk(delta="before"))
    first, second = replay.subscribe(), replay.subscribe()
    snapshot = decode(await anext(first))
    assert decode(await anext(second)) == snapshot
    replay.append(chunk(delta="after"))
    assert decode(await anext(first))["event"]["delta"] == "after"
    assert decode(await anext(second))["event"]["delta"] == "after"
    replay.append(None)
    assert decode(await anext(first))["type"] == "STREAM_END"
    assert decode(await anext(second))["type"] == "STREAM_END"
    await first.aclose()
    await second.aclose()


async def test_slow_observer_gets_reset_instead_of_silent_gap():
    replay = StreamReplay(capacity=1)
    subscriber = replay.subscribe()
    await anext(subscriber)
    replay.append(chunk(delta="a"))
    replay.append(chunk(delta="b"))
    reset = decode(await anext(subscriber))
    assert reset["type"] == "STREAM_SNAPSHOT"
    assert reset["seq"] == 2
    assert reset["events"][0]["delta"] == "ab"
    await subscriber.aclose()


async def test_reconnect_after_completion_drains_suffix_and_explicit_end():
    replay = StreamReplay()
    replay.append(chunk(delta="a"))
    replay.append(chunk(delta="b"))
    replay.append(None)
    frames = [decode(frame) async for frame in replay.subscribe(replay.run_id, 1)]
    assert [frame["type"] for frame in frames] == ["STREAM_EVENT", "STREAM_END"]
    assert frames[0]["event"]["delta"] == "b"
    assert frames[1]["persisted"] is True


@pytest.mark.parametrize("success", [True, False])
async def test_completion_waits_for_persistence_and_reports_failure(success):
    replay = StreamReplay()
    release = asyncio.Event()

    async def persist():
        await release.wait()
        return success

    replay.persistence = asyncio.create_task(persist())
    replay.append(None)
    subscriber = replay.subscribe()
    await anext(subscriber)
    terminal = asyncio.create_task(anext(subscriber))
    await asyncio.sleep(0)
    assert not terminal.done()
    release.set()
    assert decode(await terminal)["persisted"] is success
    await subscriber.aclose()


async def test_disconnecting_during_persistence_does_not_cancel_save():
    replay = StreamReplay()
    release = asyncio.Event()

    async def persist():
        await release.wait()
        return True

    replay.persistence = asyncio.create_task(persist())
    replay.append(None)
    subscriber = replay.subscribe()
    await anext(subscriber)
    terminal = asyncio.create_task(anext(subscriber))
    await asyncio.sleep(0)
    terminal.cancel()
    with pytest.raises(asyncio.CancelledError):
        await terminal
    assert not replay.persistence.cancelled()
    release.set()
    await replay.persistence


def test_split_sse_and_injected_custom_chunk():
    replay = StreamReplay()
    event = chunk(delta="你好")
    replay.append(event[:12])
    assert replay.seq == 0
    replay.append(event[12:])
    assert replay.seq == 1
    queue = _BusStreamQueue("chat")
    queue.put_nowait(("chunk", chunk("CUSTOM", name="plan_refresh")))
    assert queue.replay.events[0]["name"] == "plan_refresh"


async def test_persistence_failure_is_propagated_to_job_and_completion(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, MagicMock

    from suzent.core.chat_processor import ChatProcessor
    from suzent.database import PostProcessOutcome, PostProcessStep, StepStatus

    db = MagicMock()
    monkeypatch.setattr("suzent.core.chat_processor.get_database", lambda: db)
    processor = ChatProcessor()
    monkeypatch.setattr(
        processor, "_persist_state", AsyncMock(side_effect=OSError("disk full"))
    )
    monkeypatch.setattr(processor, "_write_transcript", AsyncMock())
    result = await processor._post_process_turn(
        chat_id="chat",
        user_id="user",
        message_content="question",
        full_response="answer",
        stream_failed=False,
        snapshot_messages=[],
        snapshot_revision=1,
        is_heartbeat=False,
        deps=SimpleNamespace(
            is_suspended=True, cancel_event=None, inline_a2ui_surfaces={}
        ),
        agent=SimpleNamespace(_model_id="test", _tool_names=[]),
        postprocess_job_id="job",
        file_snapshot=[],
    )
    assert result is False
    db.update_job_step_status.assert_any_call(
        "job", PostProcessStep.PERSIST, StepStatus.FAILED, error="disk full"
    )
    db.finalize_postprocess_job.assert_called_once_with(
        "job", PostProcessOutcome.FAILED
    )


def test_snapshot_is_immutable_and_compaction_does_not_corrupt_tail_deltas():
    replay = StreamReplay()
    replay.append(chunk(delta="a", messageId="m"))
    before = replay.read(None, None)[0]
    replay.append(chunk(delta="b", messageId="m"))
    replay.append(chunk("TEXT_MESSAGE_END", messageId="m"))
    assert before["events"][0]["delta"] == "a"
    assert replay.read(None, None)[0]["events"][0]["delta"] == "ab"
    assert replay.read(replay.run_id, 0)[0]["event"]["delta"] == "a"
    assert replay.read(replay.run_id, 1)[0]["event"]["delta"] == "b"


async def test_replacing_a_run_signals_supersession_not_successful_completion():
    from suzent.core.stream_registry import (
        register_background_stream,
        unregister_background_stream,
    )

    old = register_background_stream("replace-test")
    new = register_background_stream("replace-test")
    frames = [decode(frame) async for frame in old.replay.subscribe()]
    assert frames[-1]["superseded"] is True
    unregister_background_stream("replace-test", new)
