"""ACP session lifecycle: sub-agent teardown and config-scoped listing."""

import pytest


@pytest.mark.asyncio
@pytest.mark.parametrize("turn_fails", [False, True])
async def test_subagent_closes_its_acp_session_on_finish(turn_fails):
    """An ACP sub-agent's subprocess must not outlive the task, pass or fail."""
    from unittest.mock import AsyncMock, MagicMock, patch

    import suzent.core.subagent_runner as runner

    closed: list[str] = []
    manager = MagicMock()
    manager.close = AsyncMock(side_effect=lambda cid: closed.append(cid))

    task = runner.SubAgentTask(
        task_id="t1",
        parent_chat_id="parent",
        chat_id="subagent-t1",
        description="do a thing",
        tools_allowed=[],
        runtime="acp",
        acp_agent_id="claude-code",
    )

    db = MagicMock()
    db.get_chat.return_value = MagicMock(config={"acp_session_id": "s-9"})

    async def fake_turn(chat_id, message, config, queue):
        if turn_fails:
            raise RuntimeError("agent blew up")
        return "done"

    with (
        patch("suzent.acp.get_acp_manager", return_value=manager),
        patch("suzent.acp.runtime.run_acp_turn_text", side_effect=fake_turn),
        patch.object(runner, "_ensure_task_chat", return_value=db),
        patch.object(runner, "register_background_stream", MagicMock()),
        patch.object(runner, "unregister_background_stream", MagicMock()),
        patch.object(runner, "_broadcast_task_update", MagicMock()),
        patch.object(runner, "_persist_task_state", MagicMock()),
        patch.object(runner, "_evict_old_finished_tasks_locked", AsyncMock()),
        patch.object(runner, "_notify_parent", AsyncMock()),
        patch.object(runner, "_queue_parent_wakeup", MagicMock()),
    ):
        await runner._run_subagent(task, wakeup_parent=False)

    assert task.status == ("failed" if turn_fails else "completed")
    assert closed == ["subagent-t1"], "ACP session was left running after the task"


def test_list_chats_by_config_filters_without_loading_messages(temp_db):
    db = temp_db
    acp_id = db.create_chat("ACP one", {"runtime": "acp", "acp_agent_id": "x"})
    db.create_chat("Native one", {"runtime": "native"})
    db.create_chat("No runtime", {})
    db.append_chat_message(acp_id, {"role": "user", "content": "hello"})

    rows = db.list_chats_by_config("runtime", "acp")
    assert [r["id"] for r in rows] == [acp_id]
    assert rows[0]["title"] == "ACP one"
    assert rows[0]["config"]["acp_agent_id"] == "x"
    # Projection only -- messages are deliberately not part of the payload.
    assert "messages" not in rows[0]

    assert db.list_chats_by_config("runtime", "native")[0]["title"] == "Native one"
    assert db.list_chats_by_config("runtime", "nope") == []
