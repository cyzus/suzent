"""Legacy tool arguments must not break history restore after a schema change."""

import json

from suzent.core.agent_serializer import _restore_v3, _strip_removed_tool_args


def _history(args):
    return [
        {
            "kind": "request",
            "parts": [{"part_kind": "user-prompt", "content": "list the files"}],
        },
        {
            "kind": "response",
            "parts": [
                {
                    "part_kind": "tool-call",
                    "tool_name": "run_command",
                    "tool_call_id": "call_1",
                    "args": args,
                }
            ],
        },
    ]


def test_strips_legacy_language_from_dict_args():
    history = _history(
        {"content": "ls", "description": "List files", "language": "command"}
    )

    _strip_removed_tool_args(history)

    assert history[1]["parts"][0]["args"] == {
        "content": "ls",
        "description": "List files",
    }


def test_strips_legacy_language_from_json_string_args():
    history = _history(
        json.dumps(
            {"content": "print('hi')", "description": "Run it", "language": "python"}
        )
    )

    _strip_removed_tool_args(history)

    assert json.loads(history[1]["parts"][0]["args"]) == {
        "content": "print('hi')",
        "description": "Run it",
    }


def test_leaves_current_args_untouched():
    args = {"content": "ls", "description": "List files", "timeout": 30}
    history = _history(dict(args))

    _strip_removed_tool_args(history)

    assert history[1]["parts"][0]["args"] == args


def test_ignores_other_tools():
    history = _history({"content": "ls", "description": "d", "language": "command"})
    history[1]["parts"][0]["tool_name"] = "read_file"

    _strip_removed_tool_args(history)

    assert history[1]["parts"][0]["args"]["language"] == "command"


def test_restore_v3_accepts_history_with_legacy_language():
    raw = {
        "message_history": _history(
            {"content": "ls", "description": "d", "language": "command"}
        )
    }

    restored = _restore_v3(raw)

    assert restored is not None
    tool_call = restored["message_history"][1].parts[0]
    assert "language" not in tool_call.args_as_dict()


def test_malformed_args_do_not_raise():
    history = _history("not json at all")

    _strip_removed_tool_args(history)

    assert history[1]["parts"][0]["args"] == "not json at all"
