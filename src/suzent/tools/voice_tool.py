"""
Voice tool for speaking text.
"""

from suzent.tools.base import Tool, ToolGroup
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

    async def forward(self, text: str, prompt: str = "") -> str:
        """Speak the given text aloud using text-to-speech.

        Args:
            text: The text to speak.
            prompt: Describe the emotion and tone of the speech.
        """
        if not text:
            return "No text to speak."

        try:
            # Lazy init to avoid capturing audio device until needed
            if not self._sink:
                self._sink = SoundDeviceSink(
                    sample_rate=24000
                )  # Higher quality for TTS

            if not self._speech:
                # Use configured model or default to a reasonable one if not set
                # Use configured model or default to a reasonable one if not set
                from suzent.config import CONFIG

                model = CONFIG.tts_model or "openai/tts-1"
                voice = CONFIG.tts_voice or "alloy"

                self._speech = SpeechOutput(
                    audio_sink=self._sink,
                    tts_model=model,
                    tts_voice=voice,
                    output_rate=24000,
                )

            await self._speech.speak(text, prompt=prompt)
            return f"Spoke: {text}"

        except Exception as e:
            logger.error(f"Failed to speak: {e}")
            return f"Error speaking: {e}"
