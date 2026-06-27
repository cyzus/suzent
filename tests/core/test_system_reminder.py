import pytest
from suzent.core.system_reminder import (
    PUA_START,
    PUA_END,
    wrap_in_system_reminder,
    strip_system_reminders,
    extract_system_reminder_content,
    build_combined_reminder,
    register_global_hook,
    clear_global_hooks,
)


def test_wrap_strip_roundtrip():
    content = "hello world"
    wrapped = wrap_in_system_reminder(content)
    # default format uses invisible PUA delimiters, not XML
    assert PUA_START in wrapped
    assert PUA_END in wrapped
    assert "<system-reminder>" not in wrapped
    assert "hello world" in wrapped
    # stripping a wrapped reminder should yield an empty string
    assert strip_system_reminders(wrapped) == ""


def test_strip_pua_format():
    text = f"before{PUA_START}hidden{PUA_END}after"
    assert strip_system_reminders(text) == "beforeafter"


def test_strip_mixed_formats():
    text = f"A{PUA_START}PUA{PUA_END}B<system-reminder>XML</system-reminder>C"
    assert strip_system_reminders(text) == "ABC"


def test_extract_content_pua_and_xml():
    text = (
        f"{PUA_START}pua-content{PUA_END}<system-reminder>xml-content</system-reminder>"
    )
    extracted = extract_system_reminder_content(text)
    assert "pua-content" in extracted
    assert "xml-content" in extracted


def test_xml_fallback_via_env(monkeypatch):
    monkeypatch.setenv("SUZENT_XML_SYSTEM_REMINDER", "1")
    wrapped = wrap_in_system_reminder("hello")
    assert "<system-reminder>" in wrapped
    assert PUA_START not in wrapped
    # strip still removes the XML form
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


def test_rebuild_skips_hidden_reminder_only_prompt():
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from suzent.core.chat_processor import _rebuild_display_messages

    reminder = wrap_in_system_reminder("do not show")

    res = _rebuild_display_messages(
        [ModelRequest(parts=[UserPromptPart(content=reminder)])]
    )

    assert res == []


def test_rebuild_preserves_explicit_display_trigger():
    from pydantic_ai.messages import ModelRequest, UserPromptPart
    from suzent.core.chat_processor import _rebuild_display_messages

    reminder = wrap_in_system_reminder(
        "global hidden\n\n---\n\nScheduled Task: ingest",
        display_trigger="Scheduled Task: ingest",
    )

    res = _rebuild_display_messages(
        [ModelRequest(parts=[UserPromptPart(content=reminder)])]
    )

    assert len(res) == 1
    assert res[0]["role"] == "system_triggered"
    assert res[0]["content"] == "Scheduled Task: ingest"


# Ensure tests run
if __name__ == "__main__":
    pytest.main([__file__])
