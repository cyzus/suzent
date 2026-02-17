"""
Audio I/O implementations using sounddevice.
"""

import sounddevice as sd
import numpy as np
from suzent.logger import get_logger
from suzent.voice.types import AudioSink, AudioSource

logger = get_logger(__name__)


class SoundDeviceSink(AudioSink):
    """Audio sink that plays through system default speakers via sounddevice."""

    def __init__(self, sample_rate: int = 16000):
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


class SoundDeviceSource(AudioSource):
    """Audio source that records from system default microphone via sounddevice."""

    def __init__(self, sample_rate: int = 16000, block_size: int = 4096):
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._queue = []  # Simple list as queue not thread-safe but we play in same process usually?
        # Actually need a thread-safe queue for callback
        import queue

        self._queue = queue.Queue()

        self._stream = sd.InputStream(
            samplerate=sample_rate,
            channels=1,
            dtype="int16",
            blocksize=block_size,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time, status):
        """Callback for new audio data."""
        if status:
            logger.warning(f"Audio input status: {status}")
        self._queue.put(indata.copy().tobytes())

    def get_sample(self) -> bytes:
        """Get next chunk of audio."""
        if self._queue.empty():
            return None
        return self._queue.get()

    def close(self):
        """Clean up stream."""
        if self._stream:
            self._stream.stop()
            self._stream.close()
