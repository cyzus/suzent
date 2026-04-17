import pytest
from suzent.core.system_reminder import (
    wrap_in_system_reminder,
    strip_system_reminders,
    build_combined_reminder,
    register_global_hook,
    clear_global_hooks,
)


def test_wrap_strip_roundtrip():
    content = "hello world"
    wrapped = wrap_in_system_reminder(content)
    assert "<system-reminder>" in wrapped
    assert "hello world" in wrapped
    # stripping a wrapped reminder should yield an empty string
    assert strip_system_reminders(wrapped) == ""


def test_strip_multiple_blocks():
    text = "A<system-reminder>X</system-reminder>B<system-reminder>Y</system-reminder>C"
    assert strip_system_reminders(text) == "ABC"


def test_strip_case_insensitive():
    text = "before<SYSTEM-REMINDER>secret</SYSTEM-REMINDER>after"
    assert strip_system_reminders(text) == "beforeafter"


@pytest.mark.asyncio
async def test_hook_returns_none_produces_no_reminder():
    clear_global_hooks()

    async def null_hook(chat_id, deps):
        return None

    register_global_hook(null_hook)
    result = await build_combined_reminder("chat1", deps=None)
    assert result is None
    clear_global_hooks()


@pytest.mark.asyncio
async def test_combined_reminder_merges_global_and_adhoc():
    clear_global_hooks()

    async def global_hook(chat_id, deps):
        return "global"

    register_global_hook(global_hook)

    result = await build_combined_reminder(
        "chat1", deps=None, adhoc_reminders=["adhoc"]
    )
    clear_global_hooks()

    assert result is not None
    assert "global\n\n---\n\nadhoc" in result


def test_rebuild_strips_reminder_from_display_messages():
    from pydantic_ai.messages import ModelRequest, UserPromptPart, ToolReturnPart
    from suzent.core.chat_processor import _rebuild_display_messages

    reminder = wrap_in_system_reminder("do not show")

    # Test UserPromptPart
    msgs1 = [ModelRequest(parts=[UserPromptPart(content="user message" + reminder)])]
    res1 = _rebuild_display_messages(msgs1)
    assert res1[0]["content"] == "user message"

    # Test ToolReturnPart
    msgs2 = [
        ModelRequest(
            parts=[
                ToolReturnPart(
                    tool_name="test", content="tool result" + reminder, tool_call_id="1"
                )
            ]
        )
    ]
    res2 = _rebuild_display_messages(msgs2)
    assert res2[0]["content"] == "tool result"


# Ensure tests run
if __name__ == "__main__":
    pytest.main([__file__])
