"""Shared speech defaults and per-request validation."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class VoiceSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    autoplay: bool = True
    engine: Literal["system", "api"] = "system"
    voice: str = Field(default="", max_length=200)
    speed: float = Field(default=1, ge=0.25, le=4)
    pitch: float = Field(default=1, ge=0, le=2)
    volume: float = Field(default=1, ge=0, le=1)
    language: str = Field(default="", max_length=40)
    response_format: Literal["auto", "mp3", "wav", "opus", "aac", "flac"] = "auto"
    instructions: str = Field(default="", max_length=4000)
    realtime_model: str = Field(default="", max_length=200)
    realtime_voice: str = Field(default="", max_length=200)
    # BCP-47 code (e.g. "zh-CN") pinning speech recognition; empty = automatic.
    realtime_language: str = Field(default="", max_length=40)
    # How readily the provider's VAD hears the start of speech (Gemini only).
    # "low" keeps Suzent's own voice leaking into the mic from cutting it off.
    realtime_start_sensitivity: Literal["auto", "low", "high"] = "low"
    # Listen for a wake phrase on this machine and start a call on hearing it.
    wake_word: bool = False
    wake_phrases: list[Annotated[str, Field(max_length=40)]] = Field(
        default_factory=lambda: ["你好 Suzent", "Hey Suzent"], max_length=8
    )
    # 0..1; higher wakes more readily and more often by mistake.
    wake_sensitivity: float = Field(default=0.5, ge=0, le=1)
    # Desktop-wide shortcut that starts or ends a call, e.g.
    # "CommandOrControl+Shift+Space"; empty (the default) registers none.
    voice_hotkey: str = Field(default="", max_length=60)

    @field_validator("wake_phrases", mode="before")
    @classmethod
    def _drop_blank_phrases(cls, value: object) -> object:
        if isinstance(value, list):
            return [p.strip() for p in value if isinstance(p, str) and p.strip()]
        return value


class VoiceSettingsUpdate(VoiceSettings):
    tts_models: list[str] | None = Field(default=None, max_length=20)


def get_voice_settings() -> VoiceSettings:
    from suzent.config import CONFIG

    values = dict(CONFIG.voice_settings)
    if not values:
        from suzent.core.role_router import get_role_router

        values = {
            "engine": "api" if get_role_router().get_model_id("tts") else "system",
            "voice": CONFIG.tts_voice,
        }
    return VoiceSettings.model_validate(values)
