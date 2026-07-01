from suzent.core.context_compressor import ContextCompressor, extract_summary_body


class _Part:
    def __init__(self, content: str):
        self.content = content


class _Msg:
    def __init__(self, content: str):
        self.parts = [_Part(content)]


def test_extract_summary_body_strips_analysis_and_unwraps_summary() -> None:
    raw = "<analysis>secret reasoning</analysis>\n<summary>## 1. X\nbody</summary>"
    body = extract_summary_body(raw)
    assert "secret reasoning" not in body
    assert "<summary>" not in body and "</summary>" not in body
    assert body == "## 1. X\nbody"


def test_extract_summary_body_passthrough_without_tags() -> None:
    assert extract_summary_body("## 1. X\nbody") == "## 1. X\nbody"


def test_extract_summary_body_handles_empty_and_stray_tags() -> None:
    assert extract_summary_body("") == ""
    assert extract_summary_body("hello </summary>") == "hello"


def test_auto_compaction_plan_contains_required_fields() -> None:
    compressor = ContextCompressor(llm_client=object())
    messages = [_Msg("hello") for _ in range(2)]

    plan = compressor.get_auto_compaction_plan(messages)

    assert "can_attempt" in plan
    assert plan["messages_before"] == 2
    assert isinstance(plan["tokens_before"], int)


def test_build_auto_compaction_event_omits_none_fields() -> None:
    compressor = ContextCompressor(llm_client=object())

    payload = compressor.build_auto_compaction_event(
        stage="start",
        chat_id="chat-1",
        messages_before=10,
        tokens_before=100,
    )

    assert payload["event"] == "auto_compaction"
    assert payload["stage"] == "start"
    assert payload["chat_id"] == "chat-1"
    assert payload["messages_before"] == 10
    assert payload["tokens_before"] == 100
    assert "messages_after" not in payload
    assert "tokens_after" not in payload
