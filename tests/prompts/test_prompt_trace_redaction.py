"""The prompt trace must say what the prompt contained, not what it said.

File logging records DEBUG unconditionally, so a full-text line puts persona,
user.md, MEMORY.md, the project context.md and repository instructions on disk
on every turn. AGENTS.md forbids logging secrets or PII.
"""

from types import SimpleNamespace

import pytest

from suzent.prompts import (
    resolve_full_system_prompt,
    resolve_system_prompt_sections,
)


class _FakeRunner:
    def __init__(self, name, text):
        self.function = SimpleNamespace(__name__=name)
        self._text = text

    async def run(self, ctx):
        return self._text


class _FakeAgent:
    def __init__(self, static, runners):
        self._static = static
        self._runners = runners
        self.functions = []

    def _get_instructions(self, _):
        return self._static, self._runners

    def _get_model(self, _):
        return None

    def instructions(self, fn):
        self.functions.append(fn)
        return fn


@pytest.fixture
def agent():
    return _FakeAgent(
        "STATIC RULES",
        [
            _FakeRunner("inject_memory_context", "SECRET-PERSONA and SECRET-FACTS"),
            _FakeRunner("inject_social_context", "hello"),
        ],
    )


@pytest.mark.asyncio
async def test_sections_carry_names_and_text(agent):
    sections = await resolve_system_prompt_sections(agent, SimpleNamespace())

    assert [name for name, _ in sections] == [
        "static",
        "inject_memory_context",
        "inject_social_context",
    ]


@pytest.mark.asyncio
async def test_full_prompt_still_matches_the_joined_sections(agent):
    sections = await resolve_system_prompt_sections(agent, SimpleNamespace())
    full = await resolve_full_system_prompt(agent, SimpleNamespace())

    assert full == "\n\n".join(text for _, text in sections)


@pytest.mark.asyncio
async def test_a_trace_line_can_be_built_without_any_body_text(agent):
    """The shape the chat processor logs: names and sizes, never content."""
    sections = await resolve_system_prompt_sections(agent, SimpleNamespace())
    line = ", ".join(f"{name}:{len(text)}" for name, text in sections)

    assert "inject_memory_context:31" in line
    assert "SECRET-PERSONA" not in line
    assert "SECRET-FACTS" not in line
