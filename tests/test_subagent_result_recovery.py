"""A cancelled `agent` tool call must still name the sub-agent it started.

The streaming layer cancels a tool call at its timeout, but a sub-agent spawned
by that call keeps running. The synthesized failure is the only record the
transcript keeps, so losing the task id there leaves a live run with no way to
reach it from the UI.
"""

import json

import pytest

from suzent.core import subagent_runner
from suzent.streaming import _serialize_tool_output


class _Unserializable:
    def __repr__(self) -> str:
        return "<unserializable>"


class _JsonModeRejects:
    """A result whose metadata json mode refuses but plain dump survives."""

    def model_dump(self, mode=None):
        if mode == "json":
            raise ValueError("not json-serializable")
        return {
            "success": True,
            "message": "Sub-agent sub_abc123 completed.",
            "metadata": {"task_id": "sub_abc123", "extra": _Unserializable()},
        }


def test_serialize_tool_output_stays_json_when_json_mode_fails() -> None:
    # Previously this fell back to str(), producing a Python repr that the
    # frontend could not parse -- silently costing it task_id and status.
    raw = _serialize_tool_output(_JsonModeRejects())
    assert json.loads(raw)["metadata"]["task_id"] == "sub_abc123"


def test_serialize_tool_output_survives_unserializable_dict_values() -> None:
    raw = _serialize_tool_output({"task_id": "sub_abc123", "extra": _Unserializable()})
    assert json.loads(raw)["task_id"] == "sub_abc123"


def test_tool_call_lookup_returns_the_spawned_task() -> None:
    subagent_runner._record_spawn_for_tool_call("call-1", "sub_deadbeef")
    assert subagent_runner.task_id_for_tool_call("call-1") == "sub_deadbeef"


@pytest.mark.parametrize("missing", [None, "", "never-seen"])
def test_tool_call_lookup_is_quiet_about_unknown_calls(missing) -> None:
    assert subagent_runner.task_id_for_tool_call(missing) is None


def test_tool_call_lookup_is_bounded() -> None:
    limit = subagent_runner._SPAWN_BY_TOOL_CALL_MAX
    for i in range(limit + 25):
        subagent_runner._record_spawn_for_tool_call(f"bounded-{i}", f"sub_{i:08x}")
    assert len(subagent_runner._SPAWN_BY_TOOL_CALL) <= limit
    # The oldest entries are the ones dropped; the newest must still resolve.
    assert subagent_runner.task_id_for_tool_call(f"bounded-{limit + 24}") is not None
