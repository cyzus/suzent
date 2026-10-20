"""A failing check-in has to stay visible on the chat it belongs to.

The runner kept a single error for every chat in memory, so the status bar
named whichever chat failed last and forgot it on restart; a heartbeat that
had been failing for days still read "Heartbeat enabled".
"""

import pytest

from suzent.core.heartbeat import HEARTBEAT_OK, HeartbeatRunner


@pytest.fixture
def runner(temp_db, monkeypatch):
    monkeypatch.setattr("suzent.core.heartbeat.get_database", lambda: temp_db)
    temp_db.create_chat(
        title="Work", config={"heartbeat_enabled": True}, chat_id="hb-1"
    )
    temp_db.create_chat(
        title="Other", config={"heartbeat_enabled": True}, chat_id="hb-2"
    )
    return HeartbeatRunner()


async def test_a_failed_check_in_is_kept_on_its_chat_until_one_succeeds(
    runner, temp_db, monkeypatch
) -> None:
    async def unavailable(*args, **kwargs):
        raise RuntimeError("status_code: 404, model is no longer available")

    monkeypatch.setattr(runner, "run_bound_turn", unavailable)
    await runner._run_chat_heartbeat("hb-1", "", temp_db)

    assert "404" in runner.get_status("hb-1")["last_error"]
    assert runner.get_status("hb-2")["last_error"] is None

    async def fine(*args, **kwargs):
        return ""

    monkeypatch.setattr(runner, "run_bound_turn", fine)
    await runner._run_chat_heartbeat("hb-1", "", temp_db)

    assert runner.get_status("hb-1")["last_error"] is None
    assert runner._last_result == HEARTBEAT_OK
