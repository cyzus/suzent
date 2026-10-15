import asyncio

from suzent.core.auto_title import generate_auto_title


class _Router:
    def __init__(self, model: str | None) -> None:
        self.model = model

    def get_model_id(self, _role: str) -> str | None:
        assert _role == "title"
        return self.model


class _DB:
    def __init__(self) -> None:
        self.titles: dict[str, str] = {}

    def update_chat(self, chat_id: str, title: str) -> bool:
        self.titles[chat_id] = title
        return True


def test_generate_auto_title_updates_chat(monkeypatch) -> None:
    db = _DB()

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **_kwargs) -> str:
            return "Useful Chat Title"

    monkeypatch.setattr(
        "suzent.core.role_router.get_role_router", lambda: _Router("m1")
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)

    title = asyncio.run(generate_auto_title("chat-1", "hello"))

    assert title == "Useful Chat Title"
    assert db.titles["chat-1"] == "Useful Chat Title"


def test_generate_auto_title_tries_fallback_when_cheap_model_fails(
    monkeypatch,
) -> None:
    db = _DB()
    attempted: list[str] = []

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **_kwargs) -> str:
            attempted.append(self.model)
            if self.model == "bad-model":
                raise RuntimeError("model unavailable")
            return "Fallback Title"

    monkeypatch.setattr(
        "suzent.core.role_router.get_role_router", lambda: _Router("bad-model")
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)

    title = asyncio.run(
        generate_auto_title("chat-1", "hello", fallback_model="good-model")
    )

    assert title == "Fallback Title"
    assert attempted == ["bad-model", "good-model"]
    assert db.titles["chat-1"] == "Fallback Title"


def test_generate_auto_title_uses_local_fallback_when_models_return_empty(
    monkeypatch,
) -> None:
    db = _DB()

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **_kwargs) -> str:
            return ""

    monkeypatch.setattr(
        "suzent.core.role_router.get_role_router", lambda: _Router("m1")
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)

    title = asyncio.run(
        generate_auto_title("chat-1", "Explain why auto title is blank")
    )

    assert title == "Explain why auto title is blank"
    assert db.titles["chat-1"] == "Explain why auto title is blank"


def test_generate_auto_title_strips_system_reminders_from_model_prompt(
    monkeypatch,
) -> None:
    db = _DB()
    prompts: list[str] = []
    system_prompts: list[str] = []
    max_tokens: list[int] = []
    reasoning_efforts: list[str] = []

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **kwargs) -> str:
            prompts.append(kwargs["prompt"])
            system_prompts.append(kwargs["system"])
            max_tokens.append(kwargs["max_tokens"])
            reasoning_efforts.append(kwargs["reasoning_effort"])
            return "Greeting"

    monkeypatch.setattr(
        "suzent.core.role_router.get_role_router", lambda: _Router("m1")
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)

    title = asyncio.run(
        generate_auto_title(
            "chat-1",
            "hi\n\n<system-reminder>You have a SkillTool</system-reminder>",
        )
    )

    assert title == "Greeting"
    assert prompts == [
        "Create a title for this user message:\n<message>\nhi\n</message>\nTitle:"
    ]
    assert system_prompts == [
        "You name chat conversations. You are not replying to the user. "
        "Write the title in the primary language of the user's message. "
        "Output only a concise chat title of 3 to 6 words. "
        "No punctuation, no quotes."
    ]
    assert max_tokens == [512]
    assert reasoning_efforts == ["none"]
    assert db.titles["chat-1"] == "Greeting"


def test_generate_auto_title_strips_system_reminders_from_local_fallback(
    monkeypatch,
) -> None:
    db = _DB()

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **_kwargs) -> str:
            return ""

    monkeypatch.setattr(
        "suzent.core.role_router.get_role_router", lambda: _Router("m1")
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr("suzent.llm.LLMClient", _Client)

    title = asyncio.run(
        generate_auto_title(
            "chat-1",
            "hi\n\n<system-reminder>You have a SkillTool</system-reminder>",
        )
    )

    assert title == "hi"
    assert db.titles["chat-1"] == "hi"


async def test_hung_title_model_is_cancelled_and_uses_local_title(monkeypatch) -> None:
    from suzent.core import auto_title

    db = _DB()
    cancelled = asyncio.Event()
    attempted: list[str] = []

    async def hang(model: str, _source: str) -> str:
        attempted.append(model)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(auto_title, "TITLE_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(auto_title, "_generate_title_with_model", hang)
    monkeypatch.setattr(
        "suzent.core.role_router.get_role_router", lambda: _Router("hung")
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    title = await asyncio.wait_for(
        generate_auto_title(
            "chat", "Explain memory processing", fallback_model="primary"
        ),
        timeout=1,
    )
    assert title == "Explain memory processing"
    assert cancelled.is_set()
    assert attempted == ["hung"]
    assert db.titles["chat"] == title


async def test_reply_stream_finishes_while_title_is_pending(monkeypatch) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from pydantic_ai import Agent
    from pydantic_ai.models.test import TestModel

    from suzent import streaming
    from suzent.core.agent_deps import AgentDeps

    release = asyncio.Event()
    entered = asyncio.Event()
    tasks: list[asyncio.Task] = []
    events: list[dict] = []

    async def title(*_args, **_kwargs) -> str:
        entered.set()
        await release.wait()
        return "Late title"

    async def register(coro, **_kwargs) -> asyncio.Task:
        task = asyncio.create_task(coro)
        tasks.append(task)
        return task

    db = SimpleNamespace(
        get_chat=lambda _chat_id: SimpleNamespace(title="New Chat", turn_count=0),
        update_chat=lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr("suzent.database.get_database", lambda: db)
    monkeypatch.setattr(streaming, "get_database", lambda: db)
    monkeypatch.setattr("suzent.core.auto_title.generate_auto_title", title)
    monkeypatch.setattr("suzent.core.task_registry.register_background_task", register)
    monkeypatch.setattr("suzent.core.stream_registry.emit_bus_event", events.append)
    monkeypatch.setattr(streaming, "remove_pending_approvals", AsyncMock())
    monkeypatch.setattr(
        streaming._DraftDisplayAccumulator, "maybe_persist", AsyncMock()
    )
    agent = Agent(TestModel(custom_output_text="Reply complete"))

    async def consume() -> list[str]:
        return [
            chunk
            async for chunk in streaming.stream_agent_responses(
                agent,
                "hello",
                AgentDeps(chat_id="title-test", stateless=True),
                chat_id="title-test",
            )
        ]

    try:
        chunks = await asyncio.wait_for(consume(), timeout=1)
        assert entered.is_set()
        import json

        frames = [json.loads(chunk.removeprefix("data: ").strip()) for chunk in chunks]
        reply = "".join(frame.get("delta", "") for frame in frames)
        assert reply == "Reply complete"
        assert not tasks[0].done()
        assert "title-test" not in streaming.stream_controls
        release.set()
        await tasks[0]
        assert events == [
            {
                "event": "chat_title_updated",
                "chat_id": "title-test",
                "title": "Late title",
            }
        ]
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
