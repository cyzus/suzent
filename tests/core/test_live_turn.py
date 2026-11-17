"""The streaming turn lives in memory and a journal, never in the chat row."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from suzent import streaming
from suzent.core.live_turn import INTERRUPTED_OUTPUT, LiveTurns, fold_journal
from suzent.database import ChatDatabase


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines()]


def _assert_log_matches(db: ChatDatabase) -> None:
    assert db.chat_log_differences(db.chat_log) == {}


def _journal(live: LiveTurns, chat_id: str, run_id: str, parts: list[dict]) -> Path:
    live.record(
        chat_id, run_id, parts, started_at="2026-01-01T00:00:00+00:00", model="m"
    ).result()
    return live.path(chat_id, run_id)


def test_journal_appends_only_the_parts_that_changed(tmp_path: Path) -> None:
    live = LiveTurns(tmp_path)
    text = {"type": "text", "text": "hel"}
    tool = {"type": "tool", "toolCallId": "t1", "state": "running", "args": ""}
    path = _journal(live, "chat", "run", [text, tool])
    path = _journal(live, "chat", "run", [{**text, "text": "hello"}, tool])
    live.finish("chat", "run", "2026-01-01T00:01:00+00:00").result()

    kinds = [(line["type"], (line["data"] or {}).get("index")) for line in _lines(path)]
    assert kinds == [
        ("turn.started", None),
        ("turn.part", 0),
        ("turn.part", 1),
        ("turn.part", 0),
        ("turn.finished", None),
    ]
    turn = fold_journal(path)
    assert turn is not None and turn.finished_at == "2026-01-01T00:01:00+00:00"
    assert turn.parts[0]["text"] == "hello"


def test_fold_stops_at_a_torn_tail(tmp_path: Path) -> None:
    live = LiveTurns(tmp_path)
    path = _journal(live, "chat", "run", [{"type": "text", "text": "kept"}])
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"v": 1, "type": "turn.part", "data": {"index": 0, "pa')
    turn = fold_journal(path)
    assert turn is not None
    assert [part["text"] for part in turn.parts] == ["kept"]
    assert turn.finished_at is None


def test_fold_keeps_the_prefix_before_a_torn_multibyte_character(
    tmp_path: Path,
) -> None:
    live = LiveTurns(tmp_path)
    path = _journal(live, "chat", "run", [{"type": "text", "text": "你好"}])
    torn = '{"v": 1, "type": "turn.part", "data": {"text": "世'.encode("utf-8")[:-1]
    with path.open("ab") as handle:
        handle.write(torn)
    turn = fold_journal(path)
    assert turn is not None
    assert [part["text"] for part in turn.parts] == ["你好"]


def test_crash_mid_turn_recovers_an_interrupted_reply(temp_db: ChatDatabase) -> None:
    chat_id = temp_db.create_chat(
        title="Crash", messages=[{"role": "user", "content": "go"}], config={}
    )
    writer = LiveTurns(temp_db.chat_log.root)
    _journal(
        writer,
        chat_id,
        "run-1",
        [
            {"type": "text", "text": "Working on it"},
            {"type": "tool", "toolCallId": "t1", "state": "running", "args": "{}"},
            {
                "type": "tool",
                "toolCallId": "t2",
                "state": "approval-requested",
                "approvalId": "a2",
            },
        ],
    )
    # The process dies here: no turn.finished line is ever written.
    for journal in writer._open.values():
        journal.handle.close()

    temp_db._recover_live_turns()

    row = temp_db.get_chat(chat_id).messages[-1]
    assert row["_streaming_run_id"] == "run-1"
    assert "_streaming_draft" not in row
    assert row["interrupted"] is True
    assert row["content"] == "Working on it"
    assert row["run_finished_at"]
    tools = [part for part in row["parts"] if part["type"] == "tool"]
    assert all(part["state"] == "error" for part in tools)
    assert all(part["outcome"] == "interrupted" for part in tools)
    assert tools[0]["output"] == INTERRUPTED_OUTPUT
    assert tools[1]["approvalId"] is None
    assert not writer.journals()
    _assert_log_matches(temp_db)


def test_recovery_leaves_a_reply_that_already_landed(temp_db: ChatDatabase) -> None:
    final = {
        "role": "assistant",
        "content": "the real answer",
        "_streaming_run_id": "run-1",
    }
    chat_id = temp_db.create_chat(title="Landed", messages=[final], config={})
    live = LiveTurns(temp_db.chat_log.root)
    path = _journal(live, chat_id, "run-1", [{"type": "text", "text": "partial"}])
    live.finish(chat_id, "run-1", "2026-01-01T00:01:00+00:00").result()

    assert live.recover(temp_db, path) is False
    assert temp_db.get_chat(chat_id).messages == [final]
    assert not path.exists()


def test_recovery_drops_journals_of_deleted_chats(temp_db: ChatDatabase) -> None:
    live = LiveTurns(temp_db.chat_log.root)
    path = _journal(live, "gone", "run-1", [{"type": "text", "text": "partial"}])
    live.finish("gone", "run-1", "2026-01-01T00:01:00+00:00").result()
    assert live.recover_all(temp_db) == 0
    assert not path.exists()


def test_settle_after_landing_drops_overlay_and_journal(
    temp_db: ChatDatabase,
) -> None:
    chat_id = temp_db.create_chat(title="Settle", messages=[], config={})
    live = LiveTurns(temp_db.chat_log.root)
    live.publish(chat_id, {"_streaming_run_id": "run-1", "_streaming_draft": True})
    path = _journal(live, chat_id, "run-1", [{"type": "text", "text": "a"}])
    live.finish(chat_id, "run-1", "2026-01-01T00:01:00+00:00").result()

    live.settle(temp_db, chat_id, "run-1", landed=False, last_chance=False)
    assert path.exists() and live.overlay(chat_id) is not None

    live.settle(temp_db, chat_id, "run-1", landed=True, last_chance=False)
    assert not path.exists() and live.overlay(chat_id) is None
    assert temp_db.get_chat(chat_id).messages == []


def test_last_chance_settle_writes_the_finished_reply(temp_db: ChatDatabase) -> None:
    chat_id = temp_db.create_chat(title="Unsaved", messages=[], config={})
    live = LiveTurns(temp_db.chat_log.root)
    _journal(live, chat_id, "run-1", [{"type": "text", "text": "done"}])
    live.finish(chat_id, "run-1", "2026-01-01T00:01:00+00:00").result()

    live.settle(temp_db, chat_id, "run-1", landed=False, last_chance=True)

    row = temp_db.get_chat(chat_id).messages[-1]
    assert row["content"] == "done"
    assert row["run_finished_at"] == "2026-01-01T00:01:00+00:00"
    assert "interrupted" not in row
    _assert_log_matches(temp_db)


async def test_overlay_never_shadows_the_finished_reply(
    temp_db: ChatDatabase, monkeypatch: pytest.MonkeyPatch
) -> None:
    from suzent.routes.chat_routes import _chat_payload

    monkeypatch.setattr("suzent.database.get_database", lambda: temp_db)
    monkeypatch.setattr("suzent.routes.chat_routes.get_database", lambda: temp_db)
    final = {"role": "assistant", "content": "final", "_streaming_run_id": "run-1"}
    chat_id = temp_db.create_chat(title="Final", messages=[final], config={})
    acc = streaming._DraftDisplayAccumulator(chat_id, "run-1")
    acc.apply(
        SimpleNamespace(type="TEXT_MESSAGE_CONTENT", message_id="m", delta="late")
    )
    await acc.maybe_persist(force=True)

    messages = _chat_payload(chat_id, include_runtime=False)["messages"]
    assert [m["content"] for m in messages] == ["final"]
