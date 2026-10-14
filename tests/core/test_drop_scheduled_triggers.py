from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    UserPromptPart,
)

from suzent.core.chat_processor import _drop_unanswered_scheduled_triggers
from suzent.core.system_reminder import (
    TRIGGER_MARK,
    is_scheduled_trigger_only,
    wrap_in_system_reminder,
)

_WAKE_UP = "**Scheduled Task: daily news**\n\nSummarise today's news."
_PLACEHOLDER = f"{TRIGGER_MARK}[system trigger: {_WAKE_UP}]"
_BLOCK = wrap_in_system_reminder("run the task", display_trigger=_WAKE_UP)


def _request(text: str) -> ModelRequest:
    return ModelRequest(parts=[UserPromptPart(content=text)])


def _reply(text: str = "done") -> ModelResponse:
    return ModelResponse(parts=[TextPart(content=text)])


def test_wake_up_forms_are_recognised():
    assert is_scheduled_trigger_only(_PLACEHOLDER)
    assert is_scheduled_trigger_only(_BLOCK)
    assert not is_scheduled_trigger_only("**Scheduled Task: typed by a user")
    assert not is_scheduled_trigger_only(
        f"{TRIGGER_MARK}[system trigger: Subagent finished]"
    )
    assert not is_scheduled_trigger_only(f"{_BLOCK}\nplus user words")


def test_unanswered_wake_ups_are_dropped():
    answered = _request(_BLOCK)
    history = [
        _request(_PLACEHOLDER),
        _request(_BLOCK),
        answered,
        _reply(),
        _request(_PLACEHOLDER),
    ]

    assert _drop_unanswered_scheduled_triggers(history) == [answered, history[3]]


def test_other_requests_are_kept():
    subagent = _request(f"{TRIGGER_MARK}[system trigger: Subagent finished]")
    user = _request("hello")
    history = [subagent, user, _reply()]

    assert _drop_unanswered_scheduled_triggers(history) == history
