"""
Audio I/O implementations using sounddevice.
"""

import numpy as np
from suzent.logger import get_logger
from suzent.voice.types import AudioSink

logger = get_logger(__name__)


class SoundDeviceSink(AudioSink):
    """Audio sink that plays through system default speakers via sounddevice."""

    def __init__(self, sample_rate: int = 16000):
        import sounddevice as sd

        self._sample_rate = sample_rate
        self._stream = sd.OutputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
        )
        self._stream.start()

    def push_sample(self, data: bytes) -> None:
        """Play a chunk of audio."""
        if not data:
            return

        # Convert bytes to numpy array
        audio_data = np.frombuffer(data, dtype=np.int16)

        # Write to stream
        self._stream.write(audio_data)

    def close(self):
        """Clean up stream."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
