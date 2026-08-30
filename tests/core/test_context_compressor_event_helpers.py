from types import SimpleNamespace

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)
from pydantic_ai.usage import RequestUsage

from suzent.core.context_compressor import (
    context_overhead_tokens,
    estimate_history_tokens,
    estimate_tokens,
    ContextCompressor,
    build_live_context_usage,
    emit_context_usage_event,
    extract_summary_body,
)


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


def test_live_context_usage_omits_zero_counters() -> None:
    payload = build_live_context_usage(4200, SimpleNamespace())

    # Only the context size is known before the run reports any usage; the
    # cumulative counters stay absent so a consumer can merge this over the
    # previous turn's numbers instead of blanking them.
    assert payload == {"context_tokens": 4200}


def test_live_context_usage_carries_run_counters() -> None:
    usage = SimpleNamespace(
        input_tokens=120,
        output_tokens=30,
        cache_read_tokens=90,
        cache_write_tokens=0,
        requests=2,
        details={"reasoning_tokens": 7},
    )

    payload = build_live_context_usage(4200, usage)

    assert payload["context_tokens"] == 4200
    assert payload["input_tokens"] == 120
    assert payload["output_tokens"] == 30
    assert payload["cache_read_tokens"] == 90
    assert payload["requests"] == 2
    assert payload["total_tokens"] == 150
    assert payload["details"] == {"reasoning_tokens": 7}
    assert "cache_write_tokens" not in payload


def test_emit_context_usage_event_skips_chatless_runs(monkeypatch) -> None:
    seen: list[dict] = []
    monkeypatch.setattr(
        "suzent.core.stream_registry.emit_bus_event", lambda p: seen.append(p)
    )

    emit_context_usage_event(chat_id="", context_tokens=10)
    assert seen == []

    emit_context_usage_event(chat_id="c1", context_tokens=10)
    assert seen == [
        {"event": "context_usage", "chat_id": "c1", "usage": {"context_tokens": 10}}
    ]


def _response(input_tokens: int, text: str = ""):
    return ModelResponse(
        parts=[TextPart(content=text)],
        usage=RequestUsage(input_tokens=input_tokens),
    )


def _request(text: str):
    return ModelRequest(parts=[UserPromptPart(content=text)])


def test_estimate_counts_tool_call_arguments() -> None:
    # A file write carries the whole file in `args` and nothing in `content`.
    call = ModelResponse(
        parts=[ToolCallPart(tool_name="Write", args={"c": "q" * 4000})]
    )

    assert estimate_history_tokens([call]) > 900


def test_overhead_recovers_the_prompt_the_history_cannot_see() -> None:
    # 400 chars of history before the response, but the provider counted 9000
    # tokens — the difference is the system prompt and the tool schemas.
    history = [_request("x" * 400), _response(9000, "y" * 400), _request("z" * 800)]

    assert estimate_history_tokens(history) == 400
    assert context_overhead_tokens(history) == 8900
    assert estimate_tokens(history, 800_000).estimated_tokens == 9300


def test_overhead_is_dropped_when_the_measurement_predates_a_compaction() -> None:
    # A response whose prompt covered a long history that compaction has since
    # removed. Trusting it would keep the total pinned at the pre-compaction
    # size, and a total that cannot fall would re-trigger compaction forever.
    compacted = [_request("x" * 400), _response(600_000, "y" * 400)]

    assert context_overhead_tokens(compacted) == 0
    assert estimate_tokens(compacted, 800_000).estimated_tokens == 200


def test_overhead_is_zero_before_any_response_is_measured() -> None:
    assert context_overhead_tokens([_request("x" * 4000)]) == 0
    assert estimate_tokens([_request("x" * 4000)], 800_000).estimated_tokens == 1000
