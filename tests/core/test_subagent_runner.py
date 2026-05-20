import pytest

from suzent.core.subagent_runner import (
    SubAgentTask,
    _task_to_sse_dict,
    _wakeup_parent_batch,
)


def test_task_to_sse_dict_includes_model_override():
    task = SubAgentTask(
        task_id="sub_1",
        parent_chat_id="chat-1",
        description="Compare options",
        tools_allowed=[],
        chat_id="subagent-sub_1",
        model_override="openai/gpt-4.1",
    )

    payload = _task_to_sse_dict(task)

    assert payload["model_override"] == "openai/gpt-4.1"


@pytest.mark.asyncio
async def test_wakeup_batch_includes_models_and_synthesis_reminder(monkeypatch):
    captured = {}

    class FakeProcessor:
        async def process_background_turn(self, **kwargs):
            captured["system_reminders"] = kwargs["system_reminders"]
            return ""

    async def fake_wait_for_background_task_prefix(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "suzent.core.chat_processor.ChatProcessor",
        lambda: FakeProcessor(),
    )
    monkeypatch.setattr(
        "suzent.agent_manager.build_agent_config",
        lambda base_config, require_social_tool=False: base_config,
    )
    monkeypatch.setattr(
        "suzent.core.task_registry.wait_for_background_task_prefix",
        fake_wait_for_background_task_prefix,
    )

    batch = [
        SubAgentTask(
            task_id="sub_a",
            parent_chat_id="chat-1",
            description="Opinion A",
            tools_allowed=[],
            chat_id="subagent-sub_a",
            model_override="openai/gpt-4.1",
            status="completed",
            result_summary="Choose A.",
        ),
        SubAgentTask(
            task_id="sub_b",
            parent_chat_id="chat-1",
            description="Opinion B",
            tools_allowed=[],
            chat_id="subagent-sub_b",
            model_override="gemini/gemini-2.5-pro",
            status="completed",
            result_summary="Choose B.",
        ),
    ]

    await _wakeup_parent_batch("chat-1", batch)

    reminder = captured["system_reminders"][0]
    assert "Model: openai/gpt-4.1" in reminder
    assert "Model: gemini/gemini-2.5-pro" in reminder
    assert "Council synthesis reminder" in reminder
