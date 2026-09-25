"""Prepare on-device speech or generate a replayable audio artifact."""

import asyncio
import base64
import io
import wave
from pathlib import Path
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field, ValidationError
from pydantic_ai import RunContext

from suzent.config import CONFIG
from suzent.core.agent_deps import AgentDeps
from suzent.core.role_router import get_role_router
from suzent.llm import _litellm, _litellm_model_and_kwargs
from suzent.tools.base import Tool, ToolErrorCode, ToolGroup, ToolResult
from suzent.voice.settings import VoiceSettings, get_voice_settings


class SpeakTool(Tool):
    """Prepare speech for playback in the conversation. System speech uses the user's local device without an API; API speech saves audio. Optional arguments override global voice settings."""

    name = "SpeakTool"
    tool_name = "speak"
    group = ToolGroup.CREATIVE

    async def forward(
        self,
        ctx: RunContext[AgentDeps],
        text: Annotated[
            str,
            Field(min_length=1, max_length=20000, description="Exact text to read."),
        ],
        prompt: Annotated[
            str | None,
            Field(
                description="API model tone/style instructions; system speech cannot interpret these."
            ),
        ] = None,
        engine: Literal["system", "api"] | None = None,
        voice: Annotated[
            str | None, Field(description="System voice name/URI or API voice ID.")
        ] = None,
        speed: Annotated[float | None, Field(ge=0.25, le=4)] = None,
        pitch: Annotated[
            float | None, Field(ge=0, le=2, description="System speech only.")
        ] = None,
        volume: Annotated[
            float | None, Field(ge=0, le=1, description="Playback volume.")
        ] = None,
        language: Annotated[
            str | None, Field(description="System speech language, e.g. zh-CN.")
        ] = None,
        response_format: Literal["auto", "mp3", "wav", "opus", "aac", "flac"]
        | None = None,
    ) -> ToolResult:
        if not text.strip() or len(text) > 20000:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT, "Provide 1–20000 characters of text."
            )
        try:
            overrides = {
                key: value
                for key, value in {
                    "engine": engine,
                    "voice": voice,
                    "speed": speed,
                    "pitch": pitch,
                    "volume": volume,
                    "language": language,
                    "response_format": response_format,
                    "instructions": prompt,
                }.items()
                if value is not None
            }
            settings = VoiceSettings.model_validate(
                get_voice_settings().model_dump() | overrides
            )
            metadata = {"speech_id": uuid4().hex, "text": text, **settings.model_dump()}
            if settings.engine == "system":
                return ToolResult.success_result(
                    "System speech is ready for playback on the current device. Style instructions and output format do not apply to system speech.",
                    metadata=metadata,
                )
            if pitch is not None or language is not None:
                raise ValueError(
                    "pitch and language are system speech options; use prompt for API style guidance."
                )
            model = get_role_router().get_model_id("tts")
            if not model:
                raise ValueError(
                    "Configure Settings → Model Roles → TTS for API speech."
                )
            routed_model, auth = _litellm_model_and_kwargs(model)
            is_gemini = (
                routed_model.startswith(("gemini/", "vertex_ai/"))
                and "gemini" in routed_model
            )
            audio_format = settings.response_format
            if audio_format == "auto":
                audio_format = "wav" if is_gemini else "mp3"
            options = {}
            if is_gemini:
                if audio_format != "wav" or settings.speed != 1:
                    raise ValueError(
                        "Gemini TTS supports WAV output and no numeric speed control through this adapter. Use auto/WAV, speed 1, and prompt for pacing."
                    )
                options["voice"] = settings.voice or "Kore"
                speech_input = (
                    f"{settings.instructions}\nRead the following text aloud:\n{text}"
                    if settings.instructions
                    else text
                )
            else:
                options["response_format"] = audio_format
                speech_input = text
                if settings.voice:
                    options["voice"] = settings.voice
                elif routed_model.startswith(("openai/", "azure/")):
                    options["voice"] = "alloy"
                if settings.speed != 1:
                    options["speed"] = settings.speed
                if settings.instructions:
                    options["instructions"] = settings.instructions
            if is_gemini:
                # aspeech's bridge loses explicit credentials and leaks audio response_format into chat.
                response = await _litellm().acompletion(
                    model=routed_model,
                    messages=[{"role": "user", "content": speech_input}],
                    modalities=["audio"],
                    audio={"voice": options["voice"]},
                    **auth,
                    drop_params=False,
                    timeout=120,
                )
                audio = response.choices[0].message.audio
                if audio is None or not audio.data:
                    raise ValueError("Gemini returned no speech audio.")
                pcm = base64.b64decode(audio.data, validate=True)
                if not pcm or len(pcm) % 2:
                    raise ValueError("Gemini returned invalid PCM16 audio.")
                buffer = io.BytesIO()
                with wave.open(buffer, "wb") as wav:
                    wav.setnchannels(1)
                    wav.setsampwidth(2)
                    wav.setframerate(24000)
                    wav.writeframes(pcm)
                content = buffer.getvalue()
            else:
                response = await _litellm().aspeech(
                    model=routed_model,
                    input=speech_input,
                    **options,
                    **auth,
                    drop_params=False,
                    timeout=120,
                )
                content = response if isinstance(response, bytes) else response.content
            if not isinstance(content, bytes) or not content:
                raise ValueError("TTS returned empty audio.")
            if ctx.deps.chat_id:
                from suzent.database import get_database

                root = get_database().get_project_dir(ctx.deps.chat_id)
            else:
                root = Path(CONFIG.workspace_root)
            directory = root / "audio"
            directory.mkdir(parents=True, exist_ok=True)
            path = directory / f"speech_{uuid4().hex}.{audio_format}"
            await asyncio.to_thread(path.write_bytes, content)
            return ToolResult.success_result(
                "Speech generated and saved.",
                metadata={
                    **metadata,
                    "response_format": audio_format,
                    "saved_paths": [str(path)],
                },
            )
        except (ValidationError, ValueError) as exc:
            return ToolResult.error_result(ToolErrorCode.INVALID_ARGUMENT, str(exc))
        except Exception as exc:
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED, f"Speech generation failed: {exc}"
            )
