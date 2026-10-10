"""In-memory audio playback for the macOS server."""

import threading
import time

import miniaudio
from miniaudio import SampleFormat


class PlayObject:
    def __init__(self, samples: bytes, nchannels: int, sample_width: int, sample_rate: int):
        self._finished = threading.Event()
        self._stopped = threading.Event()
        self._closed = False
        self._lock = threading.Lock()
        self._duration = len(samples) / (nchannels * sample_width * sample_rate)
        pcm_stream = miniaudio.stream_raw_pcm_memory(samples, nchannels, sample_width)
        self._stream = self._track_completion(pcm_stream)
        next(self._stream)
        self._device = miniaudio.PlaybackDevice(
            output_format=SampleFormat.SIGNED16,
            nchannels=nchannels,
            sample_rate=sample_rate,
            buffersize_msec=50,
        )
        self._device.start(self._stream)
        self._started_at = time.monotonic()

    def _track_completion(self, pcm_stream):
        frames = yield b""
        try:
            while True:
                try:
                    chunk = pcm_stream.send(frames)
                except StopIteration:
                    return
                frames = yield chunk
        finally:
            self._finished.set()

    def _close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._device.close()

    def is_playing(self):
        return not self._closed

    def stop(self):
        self._stopped.set()
        self._finished.set()
        self._close()

    def wait_done(self):
        # The callback can consume PCM before the output device has played it.
        if self._finished.wait(self._duration + 2):
            remaining = self._duration - (time.monotonic() - self._started_at)
            self._stopped.wait(max(0, remaining) + 0.02)
        self._close()


class WaveObject:
    def __init__(self, samples: bytes, nchannels: int, sample_width: int, sample_rate: int):
        self._samples = samples
        self._nchannels = nchannels
        self._sample_width = sample_width
        self._sample_rate = sample_rate

    def play(self):
        return PlayObject(
            self._samples, self._nchannels, self._sample_width, self._sample_rate
        )
