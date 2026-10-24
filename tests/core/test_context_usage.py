from pathlib import Path
from typing import Any

import pytest
from pydantic_ai import Agent, Tool
from pydantic_ai.messages import (
    BinaryContent,
    InstructionPart,
    ModelRequest,
    ModelResponse,
    ModelMessagesTypeAdapter,
    RequestUsage,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.test import TestModel
from pydantic_ai.tools import ToolDefinition

from suzent.core.agent_deps import AgentDeps
from suzent.core.context_compressor import estimate_history_tokens, estimate_tokens
from suzent.core.context_usage import (
    ContextUsageCapability,
    build_context_breakdown,
    estimate_text,
    register_context_source,
)
from suzent.core.system_reminder import wrap_in_system_reminder


def test_project_context_is_separate_from_other_memory() -> None:
    from suzent.memory.memory_context import (
        CONTEXT_CHAR_LIMIT,
        format_core_memory_section,
    )

    deps = AgentDeps()
    text = format_core_memory_section(
        {
            "persona": "Helpful assistant",
            "facts": "Known facts",
            "context": "x" * (CONTEXT_CHAR_LIMIT + 100),
        }
    )
    register_context_source(deps, text, "memory", "core_memory")
    result = build_context_breakdown(
        [],
        ModelRequestParameters(instruction_parts=[InstructionPart(text)]),
        deps.context_sources,
        100000,
        0.8,
    )
    memory = next(row for row in result.categories if row.id == "memory")
    items = {item.name: item.tokens for item in memory.items}
    assert set(items) == {
        "persona.md",
        "MEMORY.md",
        "project_context",
        "memory_instructions",
    }
    injected_context = text.split("**Context**:\n", 1)[1].split(
        "\n## Archival Memory", 1
    )[0]
    assert items["project_context"] == estimate_text(
        "**Context**:\n" + injected_context
    )
    assert abs(memory.tokens - estimate_text(text)) <= len(items)

    unregistered = build_context_breakdown(
        [],
        ModelRequestParameters(instruction_parts=[InstructionPart(text)]),
        {},
        100000,
        0.8,
    )
    assert all(row.id != "memory" for row in unregistered.categories)


def test_source_accounting_and_deferred_visibility() -> None:
    deps = AgentDeps()
    memory = register_context_source(deps, "memory " * 20, "memory", "core_memory")
    params = ModelRequestParameters(
        instruction_parts=[InstructionPart("system"), InstructionPart(memory)],
        function_tools=[
            ToolDefinition(name="local"),
            ToolDefinition(name="remote", metadata={"suzent_context_source": "mcp"}),
            ToolDefinition(name="hidden", defer_loading=True),
            ToolDefinition(name="revealed", defer_loading=True),
        ],
        tool_visibility={
            "local": "visible",
            "remote": "visible",
            "hidden": "deferred",
            "revealed": "via_history",
        },
    )
    messages = [
        ModelRequest(parts=[UserPromptPart("hello")], instructions=memory),
        ModelResponse(parts=[ToolCallPart("local", {"command": "x" * 80}, "call")]),
        ModelRequest(
            parts=[
                ToolReturnPart("local", "result" * 20, "call"),
                ToolReturnPart("skill_execute", "skill" * 20, "skill"),
            ]
        ),
    ]
    result = build_context_breakdown(messages, params, deps.context_sources, 10000, 0.8)
    rows = {row.id: row for row in result.categories}
    assert rows["memory"].tokens == estimate_text(memory)
    assert rows["messages"].tokens == estimate_text("hello")
    assert rows["tool_results"].tokens > estimate_text("result" * 20)
    assert rows["skills"].tokens == estimate_text("skill" * 20)
    assert {item.name for item in rows["system_tools"].items} == {"local", "revealed"}
    assert result.deferred[0].items[0].name == "hidden"
    assert result.estimated_tokens == sum(row.tokens for row in result.categories)
    assert result.reserve_tokens == 2000


def test_persisted_reminder_provenance_and_compaction() -> None:
    deps = AgentDeps()
    catalog = register_context_source(
        deps, "A catalog of skills", "skills", "skills_reminder_hook"
    )
    message = ModelRequest(
        parts=[UserPromptPart("hello\n" + wrap_in_system_reminder(catalog))],
        metadata={"context_sources": deps.context_sources},
    )
    message = ModelMessagesTypeAdapter.validate_json(
        ModelMessagesTypeAdapter.dump_json([message])
    )[0]
    result = build_context_breakdown(
        [message], ModelRequestParameters(), {}, 10000, 0.8
    )
    assert next(
        row for row in result.categories if row.id == "skills"
    ).tokens == estimate_text(catalog)
    compacted = build_context_breakdown(
        [ModelRequest(parts=[UserPromptPart("summary")])],
        ModelRequestParameters(),
        deps.context_sources,
        10000,
        0.8,
    )
    assert [row.id for row in compacted.categories] == ["messages"]
    assert compacted.estimated_tokens < result.estimated_tokens


def test_media_is_not_counted_as_binary_repr() -> None:
    message = ModelRequest(
        parts=[
            UserPromptPart(
                ["look", BinaryContent(data=b"x" * 100000, media_type="image/png")]
            )
        ]
    )
    result = build_context_breakdown([message], ModelRequestParameters(), {}, 1000, 0.8)
    assert result.has_unmeasured_media
    assert result.estimated_tokens == estimate_text("look")


async def test_capability_collects_real_agent_requests_and_keeps_deps_isolated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = []
    monkeypatch.setattr(
        "suzent.core.context_compressor.emit_context_usage_event",
        lambda **kwargs: events.append(kwargs),
    )
    agent = Agent(
        TestModel(custom_output_text="done"),
        deps_type=AgentDeps,
        instructions="system",
        capabilities=[ContextUsageCapability("test")],
    )
    first = AgentDeps(chat_id="one")
    await agent.run("hello", deps=first)
    assert first.context_breakdown is not None
    assert first.context_breakdown["measured_input_tokens"] is not None
    assert {row["id"] for row in first.context_breakdown["categories"]} == {
        "messages",
        "system_prompt",
    }
    second = AgentDeps(chat_id="two")
    async with agent.run_stream("different", deps=second) as result:
        await result.get_output()
    assert second.context_breakdown is not None
    assert events[-1]["chat_id"] == "two"
    assert first.context_breakdown is not second.context_breakdown


async def test_diagnostics_failure_does_not_stop_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(*args: Any, **kwargs: Any) -> None:
        raise ValueError("bad diagnostic data")

    monkeypatch.setattr("suzent.core.context_usage.build_context_breakdown", fail)
    deps = AgentDeps(chat_id="test")
    agent = Agent(
        TestModel(custom_output_text="done"),
        deps_type=AgentDeps,
        capabilities=[ContextUsageCapability("test")],
    )
    assert (await agent.run("hello", deps=deps)).output == "done"
    assert deps.context_breakdown is None


async def test_repository_provenance_is_collected_from_actual_capability(
    tmp_path: Path,
) -> None:
    from suzent.core.repository_context import (
        RepositoryContextRoots,
        build_repo_context_capabilities,
    )

    (tmp_path / "AGENTS.md").write_text("Use pytest for tests.", encoding="utf-8")
    roots = RepositoryContextRoots(tmp_path, tmp_path, tmp_path)
    deps = AgentDeps()
    agent = Agent(
        TestModel(custom_output_text="done"),
        deps_type=AgentDeps,
        capabilities=[
            *build_repo_context_capabilities(roots),
            ContextUsageCapability("test"),
        ],
    )
    await agent.run("hello", deps=deps)
    assert deps.context_breakdown is not None
    repository = next(
        row for row in deps.context_breakdown["categories"] if row["id"] == "repository"
    )
    assert repository["items"][0]["name"] == "AGENTS.md"
    assert repository["tokens"] > 0


async def test_real_request_keeps_unloaded_tools_outside_used_context() -> None:
    def hidden_tool() -> str:
        return "result"

    deps = AgentDeps()
    agent = Agent(
        TestModel(custom_output_text="done"),
        deps_type=AgentDeps,
        tools=[Tool(hidden_tool, defer_loading=True)],
        capabilities=[ContextUsageCapability("test")],
    )
    await agent.run("hello", deps=deps)
    assert deps.context_breakdown is not None
    assert any(
        item["name"] == "hidden_tool"
        for row in deps.context_breakdown["deferred"]
        for item in row["items"]
    )
    assert not any(
        item["name"] == "hidden_tool"
        for row in deps.context_breakdown["categories"]
        for item in row["items"]
    )


def test_tool_media_is_not_serialized_into_a_text_estimate() -> None:
    message = ModelRequest(
        parts=[
            ToolReturnPart(
                "image",
                ["caption", BinaryContent(data=b"x" * 100000, media_type="image/png")],
                "call",
            )
        ]
    )
    result = build_context_breakdown([message], ModelRequestParameters(), {}, 1000, 0.8)
    assert result.has_unmeasured_media
    assert result.estimated_tokens < 100


def test_cjk_text_is_counted_near_one_token_per_character() -> None:
    assert estimate_text("abcd" * 100) == 100
    assert estimate_text("上下文窗口" * 100) == 500
    assert estimate_text("café") == 2


def test_history_estimate_does_not_quarter_chinese_text() -> None:
    history = [ModelRequest(parts=[UserPromptPart("你好" * 2000)])]

    assert estimate_history_tokens(history) == 4000


def test_history_estimate_skips_binary_media() -> None:
    history = [
        ModelRequest(
            parts=[
                UserPromptPart(
                    ["look", BinaryContent(data=b"x" * 100000, media_type="image/png")]
                )
            ]
        )
    ]

    assert estimate_history_tokens(history) == estimate_text("look")


def _schema_parameters() -> ModelRequestParameters:
    return ModelRequestParameters(
        function_tools=[
            ToolDefinition(
                name="search",
                description="d" * 4000,
                parameters_json_schema={"type": "object"},
            )
        ]
    )


def test_breakdown_counts_schemas_until_the_provider_measures_a_request() -> None:
    messages = [ModelRequest(parts=[UserPromptPart("x" * 400)])]
    result = build_context_breakdown(messages, _schema_parameters(), {}, 100_000, 0.8)

    assert result.overhead_estimate > 1000
    assert result.estimated_tokens == 100 + result.overhead_estimate
    assert result.estimated_tokens == sum(row.tokens for row in result.categories)


def test_breakdown_matches_the_compaction_trigger_once_measured() -> None:
    messages = [
        ModelRequest(parts=[UserPromptPart("x" * 400)]),
        ModelResponse(
            parts=[TextPart("y" * 400)], usage=RequestUsage(input_tokens=9000)
        ),
        ModelRequest(parts=[UserPromptPart("z" * 800)]),
    ]
    result = build_context_breakdown(messages, _schema_parameters(), {}, 100_000, 0.8)

    assert (
        result.estimated_tokens == estimate_tokens(messages, 100_000).estimated_tokens
    )
    assert result.estimated_tokens == 9300
    assert abs(sum(row.tokens for row in result.categories) - 9300) <= 3


async def test_capability_records_overhead_for_the_next_trigger(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "suzent.core.context_compressor.emit_context_usage_event", lambda **_: None
    )

    def search(query: str) -> str:
        """Search for things."""
        return query

    agent = Agent(
        TestModel(custom_output_text="done"),
        deps_type=AgentDeps,
        instructions="system " * 200,
        tools=[search],
        capabilities=[ContextUsageCapability("test")],
    )
    deps = AgentDeps(chat_id="c")
    await agent.run("hello", deps=deps)

    assert deps.context_overhead_estimate > 0
    assert deps.context_overhead_estimate == deps.context_breakdown["overhead_estimate"]
