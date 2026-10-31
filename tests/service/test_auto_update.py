"""Tests for the backend's silent-update scheduling."""

import asyncio
from datetime import datetime

from suzent.core import run_state
from suzent.service import auto_update


def _staged(tmp_path):
    state = tmp_path / ".suzent"
    state.mkdir()
    (state / "staged-update.json").write_text('{"target_tag": "v1.3.0"}')
    return tmp_path


def test_agents_idle_waits_for_recent_activity(monkeypatch):
    monkeypatch.setattr(run_state, "_chat_states", {})
    assert auto_update.agents_idle(now=10_000.0)

    state = run_state.ChatRunState()
    state.last_activity = 10_000.0 - 60
    monkeypatch.setattr(run_state, "_chat_states", {"chat": state})
    assert not auto_update.agents_idle(now=10_000.0)
    assert auto_update.agents_idle(now=10_000.0 + auto_update.IDLE_SECONDS)


def test_agents_idle_is_false_while_a_run_is_active(monkeypatch):
    async def check() -> bool:
        task = asyncio.create_task(asyncio.sleep(1))
        state = run_state.ChatRunState()
        state.active_task = task
        state.last_activity = 0
        monkeypatch.setattr(run_state, "_chat_states", {"chat": state})
        try:
            return auto_update.agents_idle(now=10_000.0)
        finally:
            task.cancel()

    assert not asyncio.run(check())


def test_service_applies_only_in_quiet_hours_when_idle(monkeypatch, tmp_path):
    root = _staged(tmp_path)
    monkeypatch.setattr(auto_update, "agents_idle", lambda now: True)
    monkeypatch.setattr(auto_update, "desktop_app_running", lambda: False)

    assert auto_update.should_apply_in_service(root, datetime(2026, 10, 26, 3, 30))
    assert not auto_update.should_apply_in_service(root, datetime(2026, 10, 26, 14, 0))

    monkeypatch.setattr(auto_update, "desktop_app_running", lambda: True)
    assert not auto_update.should_apply_in_service(root, datetime(2026, 10, 26, 3, 30))


def test_service_never_applies_without_a_staged_release(monkeypatch, tmp_path):
    monkeypatch.setattr(auto_update, "agents_idle", lambda now: True)
    monkeypatch.setattr(auto_update, "desktop_app_running", lambda: False)
    assert not auto_update.should_apply_in_service(
        tmp_path, datetime(2026, 10, 26, 3, 30)
    )


def test_auto_update_respects_the_off_switch(monkeypatch, tmp_path):
    monkeypatch.delenv("SUZENT_AUTO_UPDATE", raising=False)
    (tmp_path / ".suzent").mkdir()
    assert not auto_update._disabled_by_user(tmp_path)
    (tmp_path / ".suzent" / "auto-update").write_text("off")
    assert auto_update._disabled_by_user(tmp_path)


def test_idle_route_reports_agent_activity(monkeypatch):
    import json

    from suzent.routes.system_routes import get_system_idle

    monkeypatch.setattr(run_state, "_chat_states", {})
    response = asyncio.run(get_system_idle(None))
    assert json.loads(response.body) == {"idle": True}

    state = run_state.ChatRunState()
    state.last_activity = 1e12
    monkeypatch.setattr(run_state, "_chat_states", {"chat": state})
    response = asyncio.run(get_system_idle(None))
    assert json.loads(response.body) == {"idle": False}
