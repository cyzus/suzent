"""
Voice tool for speaking text.
"""

from typing import Annotated, Optional

from pydantic import Field
from suzent.tools.base import Tool, ToolGroup, ToolErrorCode, ToolResult
from suzent.logger import get_logger
from suzent.voice.speech import SpeechOutput
from suzent.voice.audio_io import SoundDeviceSink

logger = get_logger(__name__)


class SpeakTool(Tool):
    name = "SpeakTool"
    tool_name = "speak"
    group = ToolGroup.CREATIVE

    def __init__(self):
        self._sink = None
        self._speech = None

    async def forward(
        self,
        text: Annotated[str, Field(description="Text to speak aloud.")],
        prompt: Annotated[
            Optional[str],
            Field(
                default="",
                description="Optional tone or style guidance for the speech synthesis.",
            ),
        ] = "",
    ) -> ToolResult:
        """Speak the given text aloud using text-to-speech.

        Args:
            text: The text to speak.
            prompt: Describe the emotion and tone of the speech.
        """
        if not text:
            return ToolResult.error_result(
                ToolErrorCode.INVALID_ARGUMENT,
                "No text to speak.",
            )

        try:
            # Lazy init to avoid capturing audio device until needed
            if not self._sink:
                self._sink = SoundDeviceSink(
                    sample_rate=24000
                )  # Higher quality for TTS

            if not self._speech:
                model = None
                try:
                    from suzent.core.role_router import get_role_router

                    model = get_role_router().get_model_id("tts")
                except Exception:
                    pass

                if not model:
                    return ToolResult.error_result(
                        ToolErrorCode.EXECUTION_FAILED,
                        "No TTS model configured. Set it in Settings → Model Roles → TTS.",
                    )

                from suzent.config import CONFIG

                voice = CONFIG.tts_voice or "alloy"

                self._speech = SpeechOutput(
                    audio_sink=self._sink,
                    tts_model=model,
                    tts_voice=voice,
                    output_rate=24000,
                )

            await self._speech.speak(text, prompt=prompt)
            return ToolResult.success_result(
                f"Spoke: {text}",
                metadata={"text": text, "prompt": prompt},
            )

        except Exception as e:
            logger.error(f"Failed to speak: {e}")
            return ToolResult.error_result(
                ToolErrorCode.EXECUTION_FAILED,
                f"Error speaking: {e}",
                metadata={"text": text, "prompt": prompt},
            )
