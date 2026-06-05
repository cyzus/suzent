import asyncio

from suzent.core.auto_title import generate_auto_title


class _Router:
    def __init__(self, model: str | None) -> None:
        self.model = model

    def get_model_id(self, _role: str) -> str | None:
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

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **kwargs) -> str:
            prompts.append(kwargs["prompt"])
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
    assert prompts == ["hi"]
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
