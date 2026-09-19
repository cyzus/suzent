"""A quiet bound task's answer has to be findable when it finally has one.

A suppressible turn is not rebuilt into the transcript, so with nobody
streaming it there is otherwise nothing in the chat to show for it — and the
notification toast never renders the result text. The answer is written in
after it has been classified, never before, so the transcript never holds a
turn that a rollback still has to take back out.
"""

import pytest

from suzent.core.heartbeat import HEARTBEAT_OK, HeartbeatRunner


@pytest.fixture
def runner(temp_db, monkeypatch):
    monkeypatch.setattr("suzent.core.heartbeat.get_database", lambda: temp_db)
    temp_db.create_chat(title="Work", config={}, chat_id="chat-1")
    return HeartbeatRunner()


def answers(runner, text, *, streamed=False, temp_db=None):
    """Stub the turn itself, optionally simulating a streaming draft row."""

    async def _turn(chat_id, reminder, **kwargs):
        if streamed:
            temp_db.append_chat_message(
                chat_id,
                {"role": "assistant", "content": text, "_streaming_draft": True},
            )
        return text

    return _turn


@pytest.mark.asyncio
async def test_an_actionable_answer_is_written_into_the_chat(
    runner, temp_db, monkeypatch
):
    monkeypatch.setattr(runner, "_run_chat_turn", answers(runner, "the build is red"))

    result = await runner.run_bound_turn(
        "chat-1", "reminder", suppress_ok=True, answer_label="watch CI"
    )

    assert result == "the build is red"
    messages = temp_db.get_chat("chat-1").messages
    assert [m["role"] for m in messages] == ["system_triggered", "assistant"]
    assert messages[0]["content"] == "**Scheduled Task: watch CI**"
    assert messages[1]["content"] == "the build is red"


@pytest.mark.asyncio
async def test_a_no_op_answer_leaves_the_chat_untouched(runner, temp_db, monkeypatch):
    monkeypatch.setattr(runner, "_run_chat_turn", answers(runner, HEARTBEAT_OK))

    result = await runner.run_bound_turn(
        "chat-1", "reminder", suppress_ok=True, answer_label="watch CI"
    )

    assert result == ""
    assert temp_db.get_chat("chat-1").messages == []


@pytest.mark.asyncio
async def test_an_answer_someone_watched_stream_is_not_written_twice(
    runner, temp_db, monkeypatch
):
    """With a frontend attached the streaming draft already landed."""
    monkeypatch.setattr(
        "suzent.core.heartbeat.get_database",
        lambda: temp_db,
    )
    monkeypatch.setattr(
        runner,
        "_run_chat_turn",
        answers(runner, "the build is red", streamed=True, temp_db=temp_db),
    )

    await runner.run_bound_turn(
        "chat-1", "reminder", suppress_ok=True, answer_label="watch CI"
    )

    contents = [m["content"] for m in temp_db.get_chat("chat-1").messages]
    assert contents == ["the build is red"]


@pytest.mark.asyncio
async def test_a_heartbeat_keeps_its_own_channel(runner, temp_db, monkeypatch):
    """Heartbeat surfaces through the chat's config and its own UI, so it
    passes no label and nothing is written into the transcript."""
    monkeypatch.setattr(runner, "_run_chat_turn", answers(runner, "inbox is on fire"))

    await runner.run_bound_turn("chat-1", "reminder", suppress_ok=True)

    assert temp_db.get_chat("chat-1").messages == []


@pytest.mark.asyncio
async def test_a_speaking_task_is_not_written_in_twice(runner, temp_db, monkeypatch):
    """A task that is not suppressible persists through the ordinary path."""
    monkeypatch.setattr(runner, "_run_chat_turn", answers(runner, "the numbers"))

    await runner.run_bound_turn(
        "chat-1", "reminder", suppress_ok=False, answer_label="report"
    )

    assert temp_db.get_chat("chat-1").messages == []
