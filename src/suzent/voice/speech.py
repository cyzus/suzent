"""
Speech output — TTS via LiteLLM and audio playback through any AudioSink.

Supports any TTS provider available through LiteLLM (OpenAI, Azure, Gemini, etc.)
and provides an on_audio_chunk callback for downstream consumers (e.g., head movement).
"""

import asyncio
import io
import wave
from typing import Callable, Optional

from suzent.logger import get_logger
from suzent.voice.types import AudioSink

logger = get_logger(__name__)

# Audio output defaults
DEFAULT_OUTPUT_RATE = 16000
CHUNK_SIZE = 4096  # bytes per push to sink


class SpeechOutput:
    """Converts text to speech and plays through any audio sink.

    Args:
        audio_sink: Any object implementing AudioSink protocol (push_sample(bytes)).
        tts_model: LiteLLM model string (e.g., "openai/tts-1", "gemini/gemini-2.5-flash-preview-tts").
        tts_voice: Voice name (e.g., "alloy", "Zubenelgenubi").
        on_audio_chunk: Optional callback(bytes) for each PCM chunk during playback.
            Useful for driving reactive animations (head sway, mouth sync, etc.).
        output_rate: Sample rate expected by audio sink.
    """

    def __init__(
        self,
        audio_sink: AudioSink,
        tts_model: str,
        tts_voice: str = "alloy",
        on_audio_chunk: Optional[Callable[[bytes], None]] = None,
        output_rate: int = DEFAULT_OUTPUT_RATE,
    ):
        self._sink = audio_sink
        self._tts_model = tts_model
        self._tts_voice = tts_voice
        self._on_audio_chunk = on_audio_chunk
        self._output_rate = output_rate
        self._speaking = False
        self._stop_requested = False

    @property
    def is_speaking(self) -> bool:
        return self._speaking

    async def speak(self, text: str, prompt: str = "") -> None:
        """Convert text to speech and play through audio sink."""
        if not text.strip():
            return

        self._speaking = True
        self._stop_requested = False

        try:
            import litellm

            text = f"<TRANSCRIPT> {text} </TRANSCRIPT>"
            response = await litellm.aspeech(
                model=self._tts_model,
                input=text,
                voice=self._tts_voice,
                prompt=prompt
                or "Speak the following text in a playful and engaging manner.",
            )

            audio_bytes = self._extract_audio_bytes(response)
            if not audio_bytes:
                logger.error("TTS returned empty audio")
                return

            pcm_data = self._decode_to_pcm(audio_bytes)
            if not pcm_data:
                logger.error("Failed to decode TTS audio to PCM")
                return

            await self._play_audio(pcm_data)

        except Exception as e:
            logger.error(f"TTS/playback failed: {e}")
            raise e
        finally:
            self._speaking = False

    def stop(self) -> None:
        """Request interruption of current playback."""
        self._stop_requested = True

    def _extract_audio_bytes(self, response) -> Optional[bytes]:
        """Extract raw audio bytes from LiteLLM speech response."""
        if hasattr(response, "content"):
            return response.content
        if hasattr(response, "read"):
            return response.read()
        if isinstance(response, bytes):
            return response
        return None

    def _decode_to_pcm(self, audio_bytes: bytes) -> Optional[bytes]:
        """Decode audio to raw PCM16 at output_rate.

        Handles: WAV, MP3/other (via pydub), raw PCM fallback.
        """
        # 1) Try WAV (has RIFF header)
        if audio_bytes[:4] == b"RIFF":
            try:
                buf = io.BytesIO(audio_bytes)
                with wave.open(buf, "rb") as wf:
                    if wf.getsampwidth() == 2 and wf.getnchannels() == 1:
                        pcm = wf.readframes(wf.getnframes())
                        return self._resample_pcm(
                            pcm, wf.getframerate(), self._output_rate
                        )
            except Exception as e:
                logger.debug(f"WAV decode failed: {e}")

        # 2) Try any format via pydub + ffmpeg (MP3, OGG, AAC, etc.)
        try:
            from pydub import AudioSegment

            segment = AudioSegment.from_file(io.BytesIO(audio_bytes))
            segment = (
                segment.set_channels(1)
                .set_sample_width(2)
                .set_frame_rate(self._output_rate)
            )
            logger.debug(
                f"Decoded audio via pydub: {segment.duration_seconds:.2f}s, "
                f"{len(segment.raw_data)} bytes PCM"
            )
            return segment.raw_data
        except ImportError:
            logger.warning("pydub not installed — cannot decode TTS audio")
        except Exception as e:
            logger.debug(f"pydub decode failed: {e}")

        # 3) Last resort: assume raw PCM at 24kHz
        logger.warning("Could not decode TTS audio, treating as raw 24kHz PCM")
        return self._resample_pcm(audio_bytes, 24000, self._output_rate)

    def _resample_pcm(self, pcm_data: bytes, from_rate: int, to_rate: int) -> bytes:
        """Simple linear interpolation resampling for PCM16 mono."""
        if from_rate == to_rate:
            return pcm_data

        import numpy as np

        samples = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32)
        ratio = to_rate / from_rate
        new_length = int(len(samples) * ratio)
        indices = np.linspace(0, len(samples) - 1, new_length)
        resampled = np.interp(indices, np.arange(len(samples)), samples)
        return resampled.astype(np.int16).tobytes()

    async def _play_audio(self, pcm_data: bytes) -> None:
        """Push PCM audio to sink in chunks, firing on_audio_chunk callback."""
        offset = 0
        chunk_duration = CHUNK_SIZE / (self._output_rate * 2)  # seconds per chunk

        while offset < len(pcm_data) and not self._stop_requested:
            chunk = pcm_data[offset : offset + CHUNK_SIZE]
            offset += CHUNK_SIZE

            if self._on_audio_chunk:
                self._on_audio_chunk(chunk)

            try:
                await asyncio.to_thread(self._sink.push_sample, chunk)
            except Exception as e:
                logger.debug(f"Audio push error: {e}")
                break

            await asyncio.sleep(chunk_duration * 0.9)
