"""
Voice pipeline — audio capture, VAD-based speech segmentation, STT transcription.

Uses webrtcvad for Voice Activity Detection and LiteLLM for provider-agnostic
speech-to-text transcription. Works with any AudioSource implementation.
"""

import asyncio
import io
import time
import wave
from typing import Awaitable, Callable, Optional

from suzent.logger import get_logger
from suzent.voice.types import AudioSource

logger = get_logger(__name__)

# VAD parameters
VAD_FRAME_MS = 30  # webrtcvad frame duration (10, 20, or 30 ms)
VAD_SAMPLE_RATE = 16000
VAD_AGGRESSIVENESS = 2  # 0-3, higher = more aggressive filtering of non-speech
SILENCE_TIMEOUT_S = 1.2  # seconds of silence to end an utterance
MIN_SPEECH_DURATION_S = 0.4  # ignore very short blips


class VoicePipeline:
    """Captures audio from any source, detects speech, transcribes to text.

    Args:
        audio_source: Any object implementing AudioSource protocol (get_sample() → bytes).
        stt_model: LiteLLM model string (e.g., "whisper-1", "groq/whisper-large-v3").
        on_transcription: Async callback(text) when speech is transcribed.
        sample_rate: Audio sample rate from source.
    """

    def __init__(
        self,
        audio_source: AudioSource,
        stt_model: str,
        on_transcription: Callable[[str], Awaitable[None]],
        sample_rate: int = VAD_SAMPLE_RATE,
    ):
        self._source = audio_source
        self._stt_model = stt_model
        self._on_transcription = on_transcription
        self._sample_rate = sample_rate
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # VAD state
        self._vad = None
        self._speech_buffer: bytearray = bytearray()
        self._speech_started = False
        self._last_speech_time: float = 0.0

    async def start(self) -> None:
        """Start audio capture loop as async task."""
        if self._running:
            return

        try:
            import webrtcvad

            self._vad = webrtcvad.Vad(VAD_AGGRESSIVENESS)
        except ImportError:
            logger.error("webrtcvad not installed — voice pipeline disabled")
            return

        self._running = True
        self._task = asyncio.create_task(self._capture_loop())
        logger.info("VoicePipeline started")

    async def stop(self) -> None:
        """Stop capture loop and clean up."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("VoicePipeline stopped")

    async def _capture_loop(self) -> None:
        """Continuous audio capture → VAD → STT pipeline."""
        frame_bytes = int(self._sample_rate * VAD_FRAME_MS / 1000) * 2  # 16-bit PCM

        while self._running:
            try:
                # Get audio from source
                audio_data = await asyncio.to_thread(self._source.get_sample)
                if audio_data is None:
                    await asyncio.sleep(0.01)
                    continue

                # Ensure bytes
                if not isinstance(audio_data, (bytes, bytearray)):
                    audio_data = bytes(audio_data)

                # Process in VAD-sized frames
                offset = 0
                while offset + frame_bytes <= len(audio_data):
                    frame = audio_data[offset : offset + frame_bytes]
                    offset += frame_bytes
                    await self._process_frame(frame)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.debug(f"Voice capture error: {e}")
                await asyncio.sleep(0.1)

    async def _process_frame(self, frame: bytes) -> None:
        """Process a single VAD frame."""
        try:
            is_speech = self._vad.is_speech(frame, self._sample_rate)
        except Exception:
            return

        now = time.monotonic()

        if is_speech:
            self._last_speech_time = now
            self._speech_buffer.extend(frame)

            if not self._speech_started:
                self._speech_started = True
                logger.debug("Speech detected — recording")
        else:
            if self._speech_started:
                self._speech_buffer.extend(frame)

                # Check for silence timeout → end of utterance
                if now - self._last_speech_time > SILENCE_TIMEOUT_S:
                    duration = len(self._speech_buffer) / (self._sample_rate * 2)
                    if duration >= MIN_SPEECH_DURATION_S:
                        audio_bytes = bytes(self._speech_buffer)
                        # Reset before transcription (non-blocking)
                        self._speech_buffer = bytearray()
                        self._speech_started = False
                        await self._transcribe(audio_bytes)
                    else:
                        # Too short — discard
                        self._speech_buffer = bytearray()
                        self._speech_started = False

    async def _transcribe(self, pcm_audio: bytes) -> None:
        """Convert raw PCM audio to WAV and send to STT via LiteLLM."""
        try:
            # Wrap PCM in WAV container
            wav_buffer = io.BytesIO()
            with wave.open(wav_buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(self._sample_rate)
                wf.writeframes(pcm_audio)
            wav_buffer.seek(0)
            wav_buffer.name = "speech.wav"

            import litellm

            response = await litellm.atranscription(
                model=self._stt_model,
                file=wav_buffer,
            )

            text = ""
            if hasattr(response, "text"):
                text = response.text
            elif isinstance(response, dict):
                text = response.get("text", "")

            text = text.strip()
            if text:
                logger.info(f"Transcribed: {text[:80]}...")
                await self._on_transcription(text)

        except Exception as e:
            logger.error(f"STT transcription failed: {e}")
