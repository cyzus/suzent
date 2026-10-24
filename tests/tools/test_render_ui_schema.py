"""Cross-provider contract for the ``render_ui`` tool schema and arguments.

Nothing here calls a model. The schema is checked as the providers' own request
adapters would send it, and model behaviour is replayed through pydantic-ai's
``FunctionModel`` using payload shapes recorded from real failures:

* Anthropic sent ``component`` as a JSON *string* (the schema declared nothing).
* Gemini sent ``children: [0, 1]`` / ``[null, null]`` index lists, and fell back
  to a raw ``html`` component when typed trees kept failing.
"""

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, get_args

import pytest
from loguru import logger
from pydantic_ai import Agent
from pydantic_ai import Tool as PydanticTool
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models import ModelRequestParameters
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIResponsesModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from suzent.a2ui.models import (
    A2UIComponent,
    A2UIFormField,
    A2UITableColumn,
)
from suzent.a2ui.schema import (
    ComponentArgumentError,
    coerce_component,
    component_tool_schema,
    component_types,
)
from suzent.tools.base import ToolErrorCode
from suzent.tools.registry import _make_tool
from suzent.tools.render_ui_tool import RenderUITool

CARD = {
    "type": "card",
    "title": "Build",
    "children": [
        {"type": "text", "content": "All 1212 tests passed", "variant": "heading"},
        {"type": "badge", "label": "PASS", "color": "success"},
        {
            "type": "button",
            "label": "Open report",
            "action": "open_report",
            "context": {"run_id": 42},
        },
    ],
}


def _ctx():
    queue: asyncio.Queue = asyncio.Queue()
    return SimpleNamespace(deps=SimpleNamespace(a2ui_queue=queue)), queue


def _tool() -> PydanticTool:
    return PydanticTool(_make_tool(RenderUITool), takes_ctx=True, name="render_ui")


def _walk(node: Any):
    """Every dict/list node in a JSON-schema document."""
    yield node
    if isinstance(node, dict):
        for value in node.values():
            yield from _walk(value)
    elif isinstance(node, list):
        for value in node:
            yield from _walk(value)


# ── Schema shape (provider-neutral) ───────────────────────────────────────


def test_component_is_declared_as_an_object_with_a_type_enum():
    schema = _tool().function_schema.json_schema
    component = schema["properties"]["component"]

    assert component["type"] == "object"
    assert component["required"] == ["type"]
    assert component["properties"]["type"]["enum"] == list(component_types())
    assert "JSON OBJECT" in component["description"]


def test_other_surface_fields_are_typed_strings_and_target_is_a_closed_set():
    props = _tool().function_schema.json_schema["properties"]

    for name in ("surface_id", "title", "id"):
        assert props[name]["type"] == "string", name
    assert props["target"]["enum"] == ["canvas", "inline"]


def test_schema_has_no_refs_or_unions_that_providers_reject():
    schema = _tool().function_schema.json_schema

    assert "$defs" not in schema
    for node in _walk(schema):
        if isinstance(node, dict):
            assert "$ref" not in node
            assert "oneOf" not in node
            assert "anyOf" not in node
            assert "discriminator" not in node


def test_children_are_declared_as_objects_not_ids():
    component = _tool().function_schema.json_schema["properties"]["component"]
    children = component["properties"]["children"]

    assert children["type"] == "array"
    assert children["items"]["type"] == "object"
    assert children["items"]["required"] == ["type"]
    assert "Not an id" in children["items"]["description"]


def test_content_is_the_documented_text_field():
    props = component_tool_schema()["properties"]

    assert "content" in props
    assert "text" not in props  # accepted as an alias, never advertised


def test_schema_covers_every_component_model_field():
    """Drift guard: a field added to ``models.py`` must reach the model-facing schema."""
    props = component_tool_schema()["properties"]
    union = get_args(A2UIComponent)[0]

    assert set(component_types()) == {
        cls.model_fields["type"].default for cls in get_args(union)
    }
    for cls in get_args(union):
        for field_name, field in cls.model_fields.items():
            assert field_name in props, f"{cls.__name__}.{field_name} not in schema"
            enum = props[field_name].get("enum")
            literal = get_args(field.annotation)
            if enum and literal and all(isinstance(v, str) for v in literal):
                assert set(literal) <= set(enum), f"{cls.__name__}.{field_name}"


def test_schema_covers_nested_table_column_and_form_field_models():
    props = component_tool_schema()["properties"]
    column_props = props["columns"]["items"]["properties"]
    field_props = props["fields"]["items"]["properties"]

    for name in A2UITableColumn.model_fields:
        assert name in column_props, name
    # ``default`` is free-form (Any) and left out on purpose; everything else is shown.
    for name in set(A2UIFormField.model_fields) - {"default"}:
        assert name in field_props, name
    assert set(get_args(A2UIFormField.model_fields["type"].annotation)) == set(
        field_props["type"]["enum"]
    )


def test_model_facing_schema_is_a_fresh_copy():
    first = component_tool_schema()
    first["properties"]["type"]["enum"].append("bogus")

    assert "bogus" not in component_tool_schema()["properties"]["type"]["enum"]


@pytest.mark.parametrize(
    "build",
    [
        pytest.param(
            lambda: AnthropicModel(
                "claude-sonnet-4-5", provider=AnthropicProvider(api_key="test")
            ),
            id="anthropic",
        ),
        pytest.param(
            lambda: GoogleModel(
                "gemini-2.5-flash", provider=GoogleProvider(api_key="test")
            ),
            id="google",
        ),
        pytest.param(
            lambda: OpenAIChatModel("gpt-4o", provider=OpenAIProvider(api_key="test")),
            id="openai-chat",
        ),
        pytest.param(
            lambda: OpenAIResponsesModel(
                "gpt-4o", provider=OpenAIProvider(api_key="test")
            ),
            id="openai-responses",
        ),
    ],
)
def test_provider_request_adapters_keep_component_an_object(build):
    """What each provider adapter would actually put on the wire for this tool."""
    params = build().customize_request_parameters(
        ModelRequestParameters(function_tools=[_tool().tool_def])
    )
    sent = params.function_tools[0].parameters_json_schema
    component = sent["properties"]["component"]

    assert component["type"] == "object"
    assert component["properties"]["type"]["enum"] == list(component_types())
    assert component["properties"]["children"]["items"]["type"] == "object"
    assert "$defs" not in sent
    assert not any("$ref" in n for n in _walk(sent) if isinstance(n, dict))


# ── Argument coercion ─────────────────────────────────────────────────────


def test_coerce_passes_objects_through_untouched():
    value, was_string = coerce_component(CARD)

    assert value is CARD
    assert was_string is False


def test_coerce_parses_only_a_json_object_string():
    value, was_string = coerce_component(json.dumps(CARD))

    assert value == CARD
    assert was_string is True


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "   ",
        "hello",
        "<h1>Hi</h1>",
        "[1, 2]",
        '"just a string"',
        "42",
        "{not json",
        '{"type": "text", "content": ',
        "{" * 5000,
    ],
)
def test_coerce_rejects_everything_else_with_an_actionable_message(bad):
    with pytest.raises(ComponentArgumentError) as info:
        coerce_component(bad)

    assert "JSON object" in str(info.value)
    assert '"type": "html"' in str(info.value)


# ── Tool behaviour ────────────────────────────────────────────────────────


async def test_object_component_renders_with_children_action_and_context():
    ctx, queue = _ctx()

    result = await RenderUITool().forward(ctx, surface_id="build", component=CARD)

    assert result.success, result.message
    event = queue.get_nowait()
    assert event["event"] == "a2ui.render"
    button = event["component"]["children"][2]
    assert button["action"] == "open_report"
    assert button["context"] == {"run_id": 42}
    assert event["component"]["children"][0]["content"] == "All 1212 tests passed"


async def test_json_object_string_is_accepted_and_logs_a_deprecation():
    ctx, queue = _ctx()
    logged: list[str] = []
    sink = logger.add(lambda m: logged.append(str(m)), level="WARNING")
    try:
        result = await RenderUITool().forward(
            ctx, surface_id="build", component=json.dumps(CARD)
        )
    finally:
        logger.remove(sink)

    assert result.success, result.message
    assert queue.get_nowait()["component"]["children"][2]["action"] == "open_report"
    assert any("JSON string" in line and "deprecated" in line for line in logged)


async def test_object_component_does_not_log_a_deprecation():
    ctx, _ = _ctx()
    logged: list[str] = []
    sink = logger.add(lambda m: logged.append(str(m)), level="WARNING")
    try:
        await RenderUITool().forward(ctx, surface_id="build", component=CARD)
    finally:
        logger.remove(sink)

    assert not any("deprecated" in line for line in logged)


@pytest.mark.parametrize("bad", ["hello", "<h1>Hi</h1>", "[1, 2]", "{broken", "", "42"])
async def test_arbitrary_strings_are_rejected_and_never_rendered(bad):
    ctx, queue = _ctx()

    result = await RenderUITool().forward(ctx, surface_id="s", component=bad)

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert "JSON object" in result.message
    assert queue.empty()


async def test_stringified_component_inside_a_surface_dict_is_handled_the_same():
    ctx, queue = _ctx()

    ok = await RenderUITool().forward(
        ctx, surface={"id": "s", "component": json.dumps(CARD)}
    )
    bad = await RenderUITool().forward(ctx, surface={"id": "s", "component": "oops"})

    assert ok.success, ok.message
    assert not bad.success
    assert queue.qsize() == 1


async def test_content_is_canonical_and_text_is_still_accepted_as_alias():
    ctx, queue = _ctx()

    await RenderUITool().forward(
        ctx, surface_id="a", component={"type": "text", "content": "canonical"}
    )
    await RenderUITool().forward(
        ctx, surface_id="b", component={"type": "text", "text": "alias"}
    )

    assert queue.get_nowait()["component"]["content"] == "canonical"
    assert queue.get_nowait()["component"]["content"] == "alias"


async def test_missing_content_names_the_field():
    ctx, queue = _ctx()

    result = await RenderUITool().forward(
        ctx, surface_id="s", component={"type": "text"}
    )

    assert not result.success
    assert "component.text.content" in result.message
    assert queue.empty()


@pytest.mark.parametrize("children", [[0, 1], [None, None], ["a", "b"], [1.5]])
async def test_child_indexes_and_ids_get_a_precise_error(children):
    ctx, queue = _ctx()

    result = await RenderUITool().forward(
        ctx, surface_id="s", component={"type": "card", "children": children}
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert "component.card.children.0" in result.message
    assert "JSON object with a 'type'" in result.message
    assert queue.empty()


async def test_unknown_type_is_reported():
    ctx, _ = _ctx()

    result = await RenderUITool().forward(
        ctx, surface_id="s", component={"type": "carousel"}
    )

    assert not result.success
    assert "carousel" in result.message


async def test_flattened_component_fields_get_a_targeted_hint():
    ctx, queue = _ctx()

    result = await RenderUITool().forward(
        ctx, surface_id="s", type="card", children=[{"type": "divider"}]
    )

    assert not result.success
    assert result.error_code == ToolErrorCode.MISSING_REQUIRED_PARAM
    assert "put them inside `component`" in result.message
    assert queue.empty()


async def test_error_message_lists_problems_but_metadata_does_not_echo_input():
    ctx, _ = _ctx()
    secret = "SECRET-" + "x" * 5000

    result = await RenderUITool().forward(
        ctx,
        surface_id="s",
        component={"type": "stack", "children": [{"type": "button", "label": secret}]},
    )

    assert not result.success
    assert "component.stack.children.0.button.action" in result.message
    assert "SECRET-" not in result.message
    assert "SECRET-" not in json.dumps(result.metadata)
    assert result.metadata["errors"]


async def test_long_error_lists_are_capped():
    ctx, _ = _ctx()

    result = await RenderUITool().forward(
        ctx,
        surface_id="s",
        component={"type": "card", "children": list(range(40))},
    )

    assert not result.success
    assert result.message.count("\n- ") <= 9
    assert "more" in result.message


async def test_html_component_still_renders_and_keeps_the_action_protocol():
    ctx, queue = _ctx()
    html = (
        '<button onclick="window.parent.postMessage('
        "{type:'a2ui:action',action:'pick',context:{id:1}},'*')\">Pick</button>"
    )

    result = await RenderUITool().forward(
        ctx, surface_id="chart", component={"type": "html", "html": html, "height": 240}
    )

    assert result.success, result.message
    component = queue.get_nowait()["component"]
    assert component == {"type": "html", "html": html, "height": 240}


async def test_html_component_as_json_string_is_the_same_as_an_object():
    ctx, queue = _ctx()
    payload = {"type": "html", "html": "<p>ok</p>"}

    await RenderUITool().forward(ctx, surface_id="a", component=payload)
    await RenderUITool().forward(ctx, surface_id="b", component=json.dumps(payload))

    assert queue.get_nowait()["component"] == queue.get_nowait()["component"]


# ── Same prompt, simulated providers ──────────────────────────────────────

PROMPT = (
    "Show a status card titled 'Build' with a heading text, a success badge and "
    "a button 'Open report' that sends action open_report with run_id=42."
)

# The first call each simulated provider makes, as recorded in real transcripts.
FIRST_CALLS: dict[str, dict[str, Any]] = {
    "object (schema-following provider)": {"surface_id": "build", "component": CARD},
    "anthropic: component as JSON string": {
        "surface_id": "build",
        "component": json.dumps(CARD),
    },
    "gemini: children as indexes": {
        "surface_id": "build",
        "component": {"type": "card", "title": "Build", "children": [0, 1, 2]},
    },
    "anthropic: no component, fields flattened": {
        "surface_id": "build",
        "type": "card",
        "children": CARD["children"],
    },
    "plain-text component": {"surface_id": "build", "component": "a green card"},
}


@pytest.mark.parametrize("scenario", list(FIRST_CALLS))
async def test_every_simulated_provider_ends_with_a_rendered_surface(scenario):
    """First call per provider profile, then (if rejected) a fix guided by the error text."""
    seen_schemas: list[dict] = []
    seen_errors: list[str] = []

    def respond(messages, info: AgentInfo) -> ModelResponse:
        seen_schemas.append(info.function_tools[0].parameters_json_schema)
        returns = [
            part
            for message in messages
            for part in getattr(message, "parts", [])
            if isinstance(part, ToolReturnPart)
        ]
        if not returns:
            return ModelResponse(
                parts=[ToolCallPart("render_ui", FIRST_CALLS[scenario], "call-1")]
            )
        last = returns[-1].content
        if not last.success:
            seen_errors.append(last.message)
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        "render_ui",
                        {"surface_id": "build", "component": CARD},
                        f"call-{len(returns) + 1}",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart("done")])

    ctx_deps = SimpleNamespace(a2ui_queue=asyncio.Queue())
    agent = Agent(
        FunctionModel(respond),
        tools=[_tool()],
        deps_type=SimpleNamespace,
        instructions="Call render_ui once; if it reports an error, fix and call again.",
    )

    await agent.run(PROMPT, deps=ctx_deps)

    event = ctx_deps.a2ui_queue.get_nowait()
    assert event["component"]["children"][2]["action"] == "open_report"
    assert ctx_deps.a2ui_queue.empty()
    # Every provider is offered the identical component schema.
    assert all(s == seen_schemas[0] for s in seen_schemas)
    assert seen_schemas[0]["properties"]["component"]["type"] == "object"
    # Providers whose first call was accepted never saw an error; the others
    # were told what was wrong in the message itself, not just in metadata.
    if scenario.startswith(("object", "anthropic: component as JSON")):
        assert seen_errors == []
    else:
        assert len(seen_errors) == 1
        assert "component" in seen_errors[0]


# ── Hardening ─────────────────────────────────────────────────────────────


def test_schema_property_types_match_the_models():
    props = component_tool_schema()["properties"]

    assert props["value"]["type"] == "number"
    assert props["height"]["type"] == "integer"
    assert props["ratios"]["items"]["type"] == "number"
    assert props["rows"]["items"]["type"] == "object"
    assert props["context"]["type"] == "object"
    assert props["items"]["items"]["type"] == "string"
    for name in ("markdown", "disabled", "paged", "ordered"):
        assert props[name]["type"] == "boolean", name
    for name in ("content", "label", "action", "title", "html", "submit_label"):
        assert props[name]["type"] == "string", name


def test_schema_declares_no_defs_anywhere_inside_component():
    component = component_tool_schema()

    assert not any(
        isinstance(n, dict) and ("$defs" in n or "definitions" in n)
        for n in _walk(component)
    )


async def test_deeply_nested_json_string_never_raises_out_of_the_tool():
    ctx, queue = _ctx()
    nested = '{"a":' * 200_000  # json.loads raises RecursionError, not ValueError

    result = await RenderUITool().forward(ctx, surface_id="s", component=nested)

    assert not result.success
    assert result.error_code == ToolErrorCode.INVALID_ARGUMENT
    assert queue.empty()


def test_double_encoded_json_string_is_rejected():
    with pytest.raises(ComponentArgumentError):
        coerce_component(json.dumps(json.dumps(CARD)))


def test_surrounding_whitespace_around_a_json_object_string_is_tolerated():
    value, was_string = coerce_component("\n  " + json.dumps(CARD) + "  \n")

    assert value == CARD
    assert was_string is True


def test_trailing_garbage_after_a_json_object_is_rejected():
    with pytest.raises(ComponentArgumentError):
        coerce_component(json.dumps(CARD) + " and then some prose")


async def test_deprecation_log_never_contains_the_component_body():
    ctx, _ = _ctx()
    body = {"type": "text", "content": "TOP-SECRET-BODY"}
    logged: list[str] = []
    sink = logger.add(lambda m: logged.append(str(m)), level="DEBUG")
    try:
        result = await RenderUITool().forward(
            ctx, surface_id="s", component=json.dumps(body)
        )
    finally:
        logger.remove(sink)

    assert result.success
    assert any("deprecated" in line for line in logged)
    assert not any("TOP-SECRET-BODY" in line for line in logged)


async def test_error_report_is_capped_at_exactly_eight_lines():
    ctx, _ = _ctx()

    result = await RenderUITool().forward(
        ctx, surface_id="s", component={"type": "card", "children": list(range(40))}
    )

    lines = [ln for ln in result.message.splitlines() if ln.startswith("- ")]
    assert len(lines) == 9  # eight problems and the "... and N more" line
    assert lines[-1].startswith("- ... and 32 more")
    assert result.metadata["error_count"] == 40


async def test_oversized_error_input_does_not_inflate_message_or_metadata():
    ctx, _ = _ctx()
    huge = "SECRET-" + "x" * 1_000_000

    result = await RenderUITool().forward(ctx, surface_id="s", component={"type": huge})
    many = await RenderUITool().forward(
        ctx,
        surface_id="s",
        component={"type": "card", "children": list(range(5000))},
    )

    assert not result.success
    assert len(result.message) < 2_000
    assert len(json.dumps(result.metadata)) < 2_000
    assert len(many.metadata["errors"]) <= 20
    assert many.metadata["error_count"] == 5000
    assert all(set(e) == {"type", "loc", "msg"} for e in many.metadata["errors"])


# ── Documentation examples ────────────────────────────────────────────────

_REFERENCE = (
    Path(__file__).resolve().parents[2]
    / "skills"
    / "suzent-canvas"
    / "references"
    / "components.md"
)


def _reference_examples() -> list[dict]:
    blocks = re.findall(r"```json\n(.*?)\n```", _REFERENCE.read_text(), re.DOTALL)
    return [json.loads(b) for b in blocks if '"surface_id"' in b]


def test_reference_has_a_canonical_example_for_each_kind_of_surface():
    types = {e["component"]["type"] for e in _reference_examples()}

    assert {"card", "stack", "form", "columns", "html"} <= types


@pytest.mark.parametrize(
    "example", _reference_examples(), ids=lambda e: e["surface_id"]
)
async def test_every_json_example_in_the_skill_reference_renders(example):
    ctx, queue = _ctx()

    result = await RenderUITool().forward(ctx, **example)

    assert result.success, result.message
    assert queue.get_nowait()["id"] == example["surface_id"]
