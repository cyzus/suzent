import asyncio

import pytest

from suzent.core.input_suggestion import (
    build_transcript,
    clean_suggestion,
    suggest_next_input,
)


class _Router:
    def __init__(self, models: list[str]) -> None:
        self.models = models

    def get_model_ids(self, role: str) -> list[str]:
        assert role == "suggestion"
        return self.models


_FINISHED_TURN = [
    {"role": "user", "content": "Write a haiku about rain"},
    {"role": "assistant", "content": "Soft rain on the roof"},
]


def _patch(monkeypatch, client_cls, models: list[str] | None = None) -> None:
    router = _Router(["m1"] if models is None else models)
    monkeypatch.setattr("suzent.core.role_router.get_role_router", lambda: router)
    monkeypatch.setattr("suzent.llm.LLMClient", client_cls)


def test_transcript_needs_the_agent_to_have_the_last_word() -> None:
    assert build_transcript(_FINISHED_TURN) is not None
    assert build_transcript([*_FINISHED_TURN, {"role": "user", "content": "x"}]) is None
    assert build_transcript([{"role": "assistant", "content": "Hi!"}]) is None
    assert build_transcript([]) is None


def test_transcript_skips_empty_and_tool_only_messages() -> None:
    transcript = build_transcript(
        [
            {"role": "user", "content": "run it"},
            {"role": "assistant", "content": None, "tool_calls": [{}]},
            {"role": "system", "content": "ignored"},
            {"role": "assistant", "content": "Done."},
        ]
    )

    assert transcript is not None
    assert "ignored" not in transcript
    assert transcript.count("<assistant") == 1


def test_transcript_keeps_only_recent_messages() -> None:
    messages = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg-{i}"}
        for i in range(20)
    ]

    transcript = build_transcript(messages)

    assert transcript is not None
    assert "msg-19" in transcript
    assert "msg-10" not in transcript


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Make it longer", "Make it longer"),
        ('"Make it longer"', "Make it longer"),
        ("\n  Now translate it\nextra line", "Now translate it"),
        ("NONE", None),
        ("none.", None),
        ("", None),
        (None, None),
        ("x" * 500, None),
    ],
)
def test_clean_suggestion(raw: str | None, expected: str | None) -> None:
    assert clean_suggestion(raw) == expected


def test_suggest_next_input_returns_model_prediction(monkeypatch) -> None:
    prompts: list[str] = []

    class _Client:
        def __init__(self, model: str) -> None:
            assert model == "m1"

        async def complete(self, prompt: str, **_kwargs) -> str:
            prompts.append(prompt)
            return "Write another one about snow"

    _patch(monkeypatch, _Client)

    assert asyncio.run(suggest_next_input(_FINISHED_TURN)) == (
        "Write another one about snow"
    )
    assert "Soft rain on the roof" in prompts[0]


def test_suggest_next_input_swallows_model_errors(monkeypatch) -> None:
    class _Client:
        def __init__(self, model: str) -> None:
            pass

        async def complete(self, **_kwargs) -> str:
            raise RuntimeError("provider down")

    _patch(monkeypatch, _Client)

    assert asyncio.run(suggest_next_input(_FINISHED_TURN)) is None


def test_suggest_next_input_falls_back_to_backup_models(monkeypatch) -> None:
    tried: list[str] = []

    class _Client:
        def __init__(self, model: str) -> None:
            self.model = model

        async def complete(self, **_kwargs) -> str:
            tried.append(self.model)
            if self.model == "m1":
                raise RuntimeError("provider down")
            return "Now one about snow"

    _patch(monkeypatch, _Client, models=["m1", "m2", "m3"])

    assert asyncio.run(suggest_next_input(_FINISHED_TURN)) == "Now one about snow"
    assert tried == ["m1", "m2"]


def test_suggest_next_input_skips_the_model_when_it_cannot_help(monkeypatch) -> None:
    class _Client:
        def __init__(self, model: str) -> None:
            raise AssertionError("no model should be called")

    _patch(monkeypatch, _Client, models=[])
    assert asyncio.run(suggest_next_input(_FINISHED_TURN)) is None

    _patch(monkeypatch, _Client)
    assert asyncio.run(suggest_next_input(_FINISHED_TURN[:1])) is None
