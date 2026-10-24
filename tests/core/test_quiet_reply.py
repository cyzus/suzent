"""One rule decides that a background turn reported nothing, for every caller."""

from types import SimpleNamespace

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolSearchCallPart,
    UserPromptPart,
)

from suzent.core.heartbeat import HEARTBEAT_OK, is_quiet_reply, turn_acted
from suzent.core.scheduler import SchedulerBrain
from suzent.database.cron import normalize_delivery_mode


def _turn(*calls: ToolCallPart) -> list:
    return [
        ModelRequest(parts=[UserPromptPart(content="check in")]),
        ModelResponse(parts=list(calls)),
        ModelResponse(parts=[TextPart(content=HEARTBEAT_OK)]),
    ]


def test_quiet_reply_is_the_token_with_at_most_a_short_aside() -> None:
    assert is_quiet_reply(HEARTBEAT_OK)
    assert is_quiet_reply(f"  {HEARTBEAT_OK}\n")
    assert is_quiet_reply(f"All on track. {HEARTBEAT_OK}")
    assert not is_quiet_reply("")
    assert not is_quiet_reply("The deploy needs your approval.")
    assert not is_quiet_reply(f"{HEARTBEAT_OK} {'x' * 301}")


def test_a_turn_that_only_looked_things_up_did_not_act() -> None:
    assert not turn_acted(_turn())
    assert not turn_acted(
        _turn(
            ToolCallPart(tool_name="agent_list", args={}),
            ToolCallPart(tool_name="read_file", args={"path": "notes.md"}),
            ToolSearchCallPart(tool_name="search_tools", args={"query": "x"}),
        )
    )


def test_a_turn_that_dispatched_work_acted() -> None:
    assert turn_acted(
        _turn(ToolCallPart(tool_name="agent_dispatch", args={"agent_id": "c1"}))
    )


def test_a_quiet_reply_does_not_light_up_the_unread_badge(temp_db) -> None:
    chat = temp_db.create_chat(title="Regent", config={"unread_count": 1})
    revision = temp_db.commit_snapshot_state(chat, b"{}")

    assert temp_db.finalize_state_if_revision_matches(
        chat, revision, b"{}", count_unread=False
    )

    stored = temp_db.get_chat(chat)
    assert stored.config["unread_count"] == 1
    assert stored.turn_count == 1


def test_delivery_modes_read_as_announce_or_none(temp_db) -> None:
    assert normalize_delivery_mode("announce") == "announce"
    assert normalize_delivery_mode("silent") == "none"
    assert normalize_delivery_mode(None) == "none"

    job_id = temp_db.create_cron_job("Digest", "0 9 * * *", "p", delivery_mode="silent")
    assert temp_db.get_cron_job(job_id).delivery_mode == "none"
    temp_db.update_cron_job(job_id, delivery_mode="silent")
    assert temp_db.get_cron_job(job_id).delivery_mode == "none"


def test_cron_notifications_keep_their_job(monkeypatch) -> None:
    created: list[dict] = []
    monkeypatch.setattr(
        "suzent.core.scheduler.get_database",
        lambda: SimpleNamespace(
            create_background_notification=lambda **kw: created.append(kw)
        ),
    )

    SchedulerBrain().add_notification("cron", "Done", title="Digest", job_id=7)

    assert created == [
        {"source": "cron", "title": "Digest", "result": "Done", "job_id": 7}
    ]
