"""A `/skill <name>` turn hands the model the skill's instructions directly.

The skill rides on the user message as its own hidden block, outside the
reminder budget, so a long skill arrives whole and the transcript still shows
only what the user typed.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

import suzent.core.chat_processor as chat_processor
from suzent.core.chat_processor import ChatProcessor
from suzent.core.system_reminder import REMINDER_BUDGET_CHARS, strip_system_reminders
from suzent.skills.manager import SkillManager


@pytest.fixture
def skill_manager(tmp_path: Path) -> SkillManager:
    skill_dir = tmp_path / "skills" / "writer"
    skill_dir.mkdir(parents=True)
    body = "Use short sentences.\n" + "detail\n" * (REMINDER_BUDGET_CHARS // 4)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: writer\ndescription: Writes prose\n---\n{body}THE END\n",
        encoding="utf-8",
    )
    manager = SkillManager(skills_dir=tmp_path / "skills")
    manager.persistence_file = tmp_path / "config" / "skills.json"
    manager.enable_skill("writer")
    return manager


@pytest.fixture
def run_turn(monkeypatch: pytest.MonkeyPatch, skill_manager: SkillManager):
    prompts: list[str] = []

    class FakeAgent:
        _model_id = "model-test"
        _tool_names: list[str] = []
        _last_messages: list = []

    async def get_agent(config):
        return FakeAgent()

    async def stream(*args, message_history, **kwargs):
        prompts.append(message_history[-1].parts[0].content)
        yield 'data: {"type": "TEXT_MESSAGE_CONTENT", "delta": "ok"}\n\n'

    async def no_snapshot(self, *args, **kwargs):
        return None

    async def no_register(coro, task_id=None, description="", allow_overflow=False):
        coro.close()

    async def no_wait(prefix, timeout=None):
        return None

    chat = SimpleNamespace(messages=[], config={}, project_id=None)
    monkeypatch.setattr(chat_processor, "get_or_create_agent", get_agent)
    monkeypatch.setattr(
        chat_processor,
        "build_agent_deps",
        lambda chat_id, user_id, config: SimpleNamespace(
            last_messages=None,
            cancel_event=None,
            is_suspended=False,
            inline_a2ui_surfaces={},
            context_sources={},
            skill_manager=skill_manager,
            sandbox_enabled=False,
            stateless=True,
        ),
    )
    monkeypatch.setattr(chat_processor, "stream_agent_responses", stream)
    monkeypatch.setattr(ChatProcessor, "_persist_agent_state_snapshot", no_snapshot)
    monkeypatch.setattr(
        "suzent.core.task_registry.register_background_task", no_register
    )
    monkeypatch.setattr(
        "suzent.core.task_registry.wait_for_background_task_prefix", no_wait
    )
    monkeypatch.setattr(
        chat_processor,
        "get_database",
        lambda: SimpleNamespace(
            get_chat=lambda chat_id: chat,
            append_display_rows=lambda chat_id, rows: None,
        ),
    )

    async def run(message: str) -> str:
        async for _ in ChatProcessor().process_turn(
            chat_id="chat-1", user_id="user-1", message_content=message
        ):
            pass
        [prompt] = prompts
        return prompt

    return run


async def test_the_whole_skill_reaches_the_model(run_turn) -> None:
    prompt = await run_turn("/skill writer draft a note")

    assert "Use short sentences." in prompt
    assert "THE END" in prompt
    assert "[truncated" not in prompt


async def test_the_transcript_shows_only_what_was_typed(run_turn) -> None:
    prompt = await run_turn("/skill writer draft a note")

    assert strip_system_reminders(prompt) == "/skill writer draft a note"
