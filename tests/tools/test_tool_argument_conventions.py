"""Conventions every registered tool's arguments follow.

These are the properties an audit had to rediscover by generating all 31
schemas by hand: that each tool tells the model what it is for, that each
argument says what it means, and that a closed set of values is declared as a
closed set instead of described in prose. Each one was broken somewhere before
this file existed, so each is pinned here rather than left to review.
"""

import ast
import inspect
import pathlib
import textwrap
from typing import get_args

import pytest
from pydantic_ai import Tool as PydanticTool

from suzent.tools.agents.agent_tool import SubagentType, _SUBAGENT_PROFILES
from suzent.tools.registry import _all_tool_classes, _make_tool
from suzent.tools.schedule_tool import ScheduleAction

TOOLS_ROOT = pathlib.Path(__file__).resolve().parents[2] / "src" / "suzent" / "tools"


def _tool_defs():
    """``(class, ToolDefinition)`` for every registered tool, as the agent builds it."""
    for cls in _all_tool_classes():
        built = _make_tool(cls)
        tool = built if isinstance(built, PydanticTool) else PydanticTool(built)
        yield cls, tool.tool_def


ALL = list(_tool_defs())
ALL_IDS = [cls.name for cls, _ in ALL]


@pytest.mark.parametrize("cls,tool_def", ALL, ids=ALL_IDS)
def test_tool_has_a_model_facing_description(cls, tool_def):
    """A tool with no description is advertised to the model by name alone.

    Ten tools shipped that way, and ``functools.wraps`` silently dropped four
    more whose ``forward()`` inherits its docstring instead of declaring one.
    They were discoverable in the picker and invisible in the ToolSearch pool.
    """
    assert (tool_def.description or "").strip(), (
        f"{cls.name} reaches the model with no description; give forward() a "
        f"docstring or the class one, which the capability catalog falls back to"
    )


@pytest.mark.parametrize("cls,tool_def", ALL, ids=ALL_IDS)
def test_every_argument_describes_itself(cls, tool_def):
    undescribed = sorted(
        name
        for name, spec in (
            tool_def.parameters_json_schema.get("properties") or {}
        ).items()
        if not (spec.get("description") or "").strip()
    )
    assert not undescribed, (
        f"{cls.name} exposes {undescribed} with no description. Put it in "
        f"Field(description=...) -- a bare name is all the model gets."
    )


def _forward_annotations():
    """``(label, annotation source)`` for every Tool.forward parameter."""
    for path in sorted(TOOLS_ROOT.rglob("*.py")):
        src = path.read_text()
        for cls in [n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.ClassDef)]:
            for fn in cls.body:
                if (
                    not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
                    or fn.name != "forward"
                ):
                    continue
                for arg in fn.args.args[1:]:
                    if arg.arg == "ctx" or not arg.annotation:
                        continue
                    segment = ast.get_source_segment(src, arg.annotation) or ""
                    yield f"{cls.name}.{arg.arg}", segment


def test_no_default_inside_field():
    """``Field(default=X)`` beside a signature default is dead metadata.

    The signature default wins and Field's copy is discarded, so the two can
    drift with nothing to catch it. 57 parameters carried both.
    """
    offenders = [
        label
        for label, ann in _forward_annotations()
        if "Field(default=" in ann.replace("\n", "").replace(" ", "")
    ]
    assert not offenders, (
        f"{offenders} set a default inside Field(); the signature default is "
        f"the one that takes effect, so declare it only there"
    )


@pytest.mark.parametrize("cls,tool_def", ALL, ids=ALL_IDS)
def test_closed_sets_are_inlined_not_referenced(cls, tool_def):
    """A closed set should be a ``Literal``, which inlines as ``enum``.

    An ``enum.Enum`` parameter is hoisted into ``$defs`` and referenced by
    ``$ref`` instead, which providers handle less consistently. A nested
    ``BaseModel`` is hoisted too and is fine -- that is how a structured
    argument is meant to be expressed -- so only enum definitions are rejected.
    """
    hoisted_enums = sorted(
        name
        for name, spec in (tool_def.parameters_json_schema.get("$defs") or {}).items()
        if "enum" in spec
    )
    assert not hoisted_enums, (
        f"{cls.name} hoists {hoisted_enums} into $defs; use Literal[...] rather "
        f"than an enum.Enum parameter so the values inline"
    )


def test_subagent_profiles_match_their_literal():
    assert set(get_args(SubagentType)) == set(_SUBAGENT_PROFILES), (
        "SubagentType and _SUBAGENT_PROFILES disagree; the schema would offer a "
        "profile the resolver rejects, or hide one it accepts"
    )


def test_every_schedule_action_is_dispatched():
    """Each ``ScheduleAction`` member must have a branch in ScheduleTool.forward."""
    from suzent.tools.schedule_tool import ScheduleTool

    tree = ast.parse(textwrap.dedent(inspect.getsource(ScheduleTool.forward)))
    handled = {
        node.comparators[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and isinstance(node.left, ast.Name)
        and node.left.id == "action"
        and isinstance(node.comparators[0], ast.Constant)
    }
    assert set(get_args(ScheduleAction)) == handled, (
        f"ScheduleAction offers {sorted(set(get_args(ScheduleAction)) - handled)} "
        f"with no branch handling it"
    )
