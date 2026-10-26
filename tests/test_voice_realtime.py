import pytest
from pydantic import ValidationError

from suzent.voice.realtime import (
    MissingApiKey,
    NoRealtimeModel,
    UnsupportedProvider,
    build_startup_context,
    list_realtime_options,
    normalize_transcript,
    resolve_realtime_model,
)
from suzent.voice.settings import VoiceSettings


def test_voice_settings_validate_realtime_fields():
    settings = VoiceSettings(
        realtime_model="openai/gpt-realtime", realtime_voice="alloy"
    )
    assert settings.realtime_model == "openai/gpt-realtime"
    with pytest.raises(ValidationError):
        VoiceSettings(realtime_model="x" * 201)
    with pytest.raises(ValidationError):
        VoiceSettings(realtime_language="x" * 41)


def test_realtime_model_mapping_and_errors(monkeypatch):
    monkeypatch.setattr(
        "suzent.voice.realtime.resolve_api_key",
        lambda provider: "key" if provider == "openai" else None,
    )
    model_id, model = resolve_realtime_model(VoiceSettings())
    assert model_id == "openai/gpt-realtime"
    assert model.model_name == "gpt-realtime"

    with pytest.raises(MissingApiKey):
        resolve_realtime_model(VoiceSettings(realtime_model="xai/grok-voice-latest"))
    with pytest.raises(UnsupportedProvider):
        resolve_realtime_model(VoiceSettings(realtime_model="anthropic/voice"))
    with pytest.raises(UnsupportedProvider):
        resolve_realtime_model(VoiceSettings(realtime_model="openai/not-a-model"))

    monkeypatch.setattr("suzent.voice.realtime.resolve_api_key", lambda _provider: None)
    with pytest.raises(NoRealtimeModel):
        resolve_realtime_model(VoiceSettings())


def test_gemini_default_is_3_8_live_and_pins_language(monkeypatch):
    monkeypatch.setattr(
        "suzent.voice.realtime.resolve_api_key",
        lambda provider: "key" if provider == "gemini" else None,
    )
    model_id, _model = resolve_realtime_model(VoiceSettings())
    assert model_id == "gemini/gemini-3.8-live"
    _id, model = resolve_realtime_model(VoiceSettings(realtime_language="zh-CN"))
    assert model.settings["google_transcription_language_codes"] == ["zh-CN"]


def test_gemini_start_sensitivity_defaults_low_and_can_be_left_to_the_provider(
    monkeypatch,
):
    monkeypatch.setattr("suzent.voice.realtime.resolve_api_key", lambda _p: "key")
    _id, model = resolve_realtime_model(
        VoiceSettings(realtime_model="gemini/gemini-3.8-live")
    )
    assert model.settings["google_vad"] == {"start_sensitivity": "low"}
    _id, model = resolve_realtime_model(
        VoiceSettings(
            realtime_model="gemini/gemini-3.8-live", realtime_start_sensitivity="auto"
        )
    )
    assert "google_vad" not in model.settings
    _id, model = resolve_realtime_model(
        VoiceSettings(realtime_model="openai/gpt-realtime")
    )
    assert "google_vad" not in model.settings
    with pytest.raises(ValueError):
        VoiceSettings(realtime_start_sensitivity="medium")


def test_realtime_options_say_which_models_stream_captions(monkeypatch):
    monkeypatch.setattr(
        "suzent.voice.realtime.get_configured_provider_ids",
        lambda: {"openai", "gemini", "xai"},
    )
    live = {o["id"]: o["live_captions"] for o in list_realtime_options()}
    assert live["gemini/gemini-2.5-flash-native-audio-latest"] is True
    assert live["gemini/gemini-3.1-flash-live-preview"] is False
    assert live["openai/gpt-realtime"] is None  # never measured: no claim


def test_realtime_options_come_from_configured_providers_capabilities(monkeypatch):
    monkeypatch.setattr(
        "suzent.voice.realtime.get_configured_provider_ids",
        lambda: {"gemini", "google", "dashscope"},
    )
    ids = [o["id"] for o in list_realtime_options()]
    assert ids[0] == "gemini/gemini-3.8-live"  # the provider default leads
    assert "gemini/gemini-3.1-flash-live-preview" in ids
    assert all(i.startswith("gemini/") for i in ids)
    # Live models without realtime endpoint data are not offered.
    assert "gemini/gemini-2.5-flash" not in ids


def test_realtime_options_include_models_found_only_in_capability_data(monkeypatch):
    monkeypatch.setattr(
        "suzent.voice.realtime.get_configured_provider_ids", lambda: {"xai"}
    )
    ids = {o["id"] for o in list_realtime_options()}
    assert {"xai/grok-voice-latest", "xai/grok-voice-3.0"} <= ids
    monkeypatch.setattr("suzent.voice.realtime.resolve_api_key", lambda _p: "key")
    _id, model = resolve_realtime_model(
        VoiceSettings(realtime_model="openai/gpt-realtime-mini")
    )
    assert model.model_name == "gpt-realtime-mini"


def test_realtime_options_empty_without_configured_providers(monkeypatch):
    monkeypatch.setattr("suzent.voice.realtime.get_configured_provider_ids", set)
    assert list_realtime_options() == []


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("<noise> 你好 世界 ", "你好世界"),
        ("今天天气怎么样?", "今天天气怎么样？"),
        ("我想,查一下", "我想，查一下"),
        # Gemini 3.1 output, measured 2026-10-23.
        ("明天伦敦天气怎么样 ? 要不要带伞 ?", "明天伦敦天气怎么样？要不要带伞？"),
        ("Python 3. 8", "Python 3. 8"),
        ("版本 3.8 发布", "版本 3.8 发布"),
        ("好的, OK", "好的，OK"),
        # Not sentence punctuation: emoticons, ellipses, times.
        ("你好 :)", "你好 :)"),
        ("好的...", "好的..."),
        ("时间 10:30", "时间 10:30"),
        ("hello  world", "hello world"),
        ("<unk>", ""),
    ],
)
def test_normalize_transcript(raw, clean):
    assert normalize_transcript(raw) == clean


def test_startup_context_keeps_recent_visible_turns_only():
    rows = [
        {"role": "user", "content": "first"},
        {"role": "tool", "content": "secret tool output"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": ""},
        "garbage",
    ]
    context = build_startup_context(rows)
    assert context.startswith("[BACKEND]")
    assert "user: first\nassistant: reply" in context
    assert "secret" not in context
    assert build_startup_context([]) == ""
    assert build_startup_context(None) == ""


def test_startup_context_is_bounded_and_keeps_newest():
    rows = [{"role": "user", "content": f"msg{i} " + "x" * 2000} for i in range(50)]
    context = build_startup_context(rows)
    assert len(context) < 13_000
    assert "msg49" in context and "msg0 " not in context
