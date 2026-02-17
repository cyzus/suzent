"""
Voice tool for speaking text.
"""

from smolagents.tools import Tool
from suzent.logger import get_logger
from suzent.voice.speech import SpeechOutput
from suzent.voice.audio_io import SoundDeviceSink

logger = get_logger(__name__)


class SpeakTool(Tool):
    name = "speak_tool"
    description = "Speaks the given text using text-to-speech."
    inputs = {
        "text": {"type": "string", "description": "The text to speak."},
        "prompt": {
            "type": "string",
            "description": "Describe the emotion and tone of the speech.",
            "nullable": True,
        },
    }
    output_type = "string"
    is_initialized = False

    def __init__(self):
        self._sink = None
        self._speech = None

    def forward(self, text: str, prompt: str = "") -> str:
        """Speaks the text."""
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

            # Run async speak in a format compatible with synchronous tool
            import asyncio

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            loop.run_until_complete(self._speech.speak(text))
            return f"Spoke: {text}"

        except Exception as e:
            logger.error(f"Failed to speak: {e}")
            return f"Error speaking: {e}"
