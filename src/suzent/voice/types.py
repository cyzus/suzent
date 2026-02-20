"""
Audio I/O protocols for voice pipeline and speech output.

These abstract away hardware-specific audio sources (mic) and sinks (speaker)
so the voice pipeline can work with any audio backend — robot mic, desktop mic,
WebRTC stream, etc.
"""

from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class AudioSource(Protocol):
    """Provides audio data from an input device (mic, stream, file, etc.)."""

    def get_sample(self) -> Optional[bytes]:
        """Read a chunk of PCM16 audio (blocking). Returns None if no data available."""
        ...


@runtime_checkable
class AudioSink(Protocol):
    """Sends audio data to an output device (speaker, stream, file, etc.)."""

    def push_sample(self, data: bytes) -> None:
        """Push a chunk of PCM16 audio for playback (blocking)."""
        ...
