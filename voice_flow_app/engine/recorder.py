"""录音模块 — sounddevice InputStream，麦克风采集"""
import queue
import time
from typing import Optional, Callable

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = 'int16'
MIN_DURATION = 0.5

# FFT 预计算
_FFT_WINDOW = np.hanning(1024)  # 固定 1024 点 Hann 窗

# 对数频率映射：64 个 bin，语音低频更密
_FFT_BINS = 64
_BIN_EDGES = np.unique(np.logspace(
    np.log10(50), np.log10(7900), _FFT_BINS + 1
).astype(int))


class Recorder:
    """音频录制器 — 麦克风采集 + 同时喂入多个流式 STT 引擎"""

    def __init__(self,
                 level_callback: Optional[Callable[[float], None]] = None,
                 spectrum_callback: Optional[Callable[[list], None]] = None):
        self._audio_queue: queue.Queue = queue.Queue()
        self._stream: Optional[sd.InputStream] = None
        self._recording = False
        self._start_time = 0.0
        self._last_duration = 0.0
        self._streaming_stts: list = []
        self._level_cb = level_callback
        self._spectrum_cb = spectrum_callback

    def add_streaming_stt(self, stt):
        self._streaming_stts.append(stt)

    def clear_streaming_stts(self):
        self._streaming_stts.clear()

    # ── 回调：麦克风（含电平 + 频谱） ──

    def _callback(self, indata, frames, time_info, status):
        if not self._recording:
            return
        data = indata.copy()
        self._audio_queue.put(data)
        # 计算音频电平 (RMS)
        if self._level_cb:
            rms = np.sqrt(np.mean(data.astype(np.float32) ** 2))
            level = min(1.0, rms / 1800.0)
            self._level_cb(level)
        # 计算频谱 (FFT)
        if self._spectrum_cb:
            chunk = data[:1024, 0].astype(np.float32) / 32768.0
            if len(chunk) < 1024:
                chunk = np.pad(chunk, (0, 1024 - len(chunk)))
            windowed = chunk * _FFT_WINDOW
            fft = np.abs(np.fft.rfft(windowed))[:513]
            mags = np.zeros(_FFT_BINS, dtype=np.float32)
            for j in range(_FFT_BINS):
                lo, hi = _BIN_EDGES[j], _BIN_EDGES[j + 1]
                if hi > len(fft):
                    hi = len(fft)
                if hi > lo:
                    mags[j] = np.mean(fft[lo:hi])
            mags = np.log1p(mags * 10)
            mx = mags.max()
            if mx > 1e-8:
                mags /= mx
            self._spectrum_cb(mags.tolist())
        # 喂给所有流式 STT 引擎
        pcm = indata.tobytes()
        for stt in self._streaming_stts:
            try:
                stt.feed(pcm)
            except Exception:
                pass

    # ── 启动 / 停止 ──

    def start(self):
        self._audio_queue = queue.Queue()
        self._recording = True
        self._start_time = time.time()
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=CHANNELS,
            dtype=DTYPE, callback=self._callback,
        )
        self._stream.start()

    def stop(self) -> Optional[np.ndarray]:
        self._last_duration = time.time() - self._start_time if self._recording else 0.0
        self._recording = False
        if self._stream:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
        self._stream = None

        chunks = []
        while True:
            try:
                chunks.append(self._audio_queue.get_nowait())
            except queue.Empty:
                break

        if not chunks:
            return None

        audio = np.concatenate(chunks, axis=0).flatten()
        duration = len(audio) / SAMPLE_RATE
        if duration < MIN_DURATION:
            return None
        return audio

    @property
    def duration(self) -> float:
        if self._recording:
            return time.time() - self._start_time
        return self._last_duration
