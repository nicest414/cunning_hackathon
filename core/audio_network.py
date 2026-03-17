"""高周波 Audio FSK を用いたオフライン P2P 多数決モジュール。

選択肢ごとに以下の周波数を使用:
  1: 18000 Hz
  2: 18500 Hz
  3: 19000 Hz
  4: 19500 Hz

送信: numpy でサイン波を生成し pyaudio でスピーカーから再生。
受信: pyaudio でマイク入力を常時監視し、FFT でピーク周波数を検出。
"""

import threading
from collections import Counter
from typing import Callable

try:
    import numpy as np
    import pyaudio
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False


SAMPLE_RATE = 44100
TONE_DURATION = 0.3        # 送信トーン長（秒）
CHUNK_SIZE = 4096          # 受信チャンクサイズ（サンプル数）
FREQ_TOLERANCE = 200       # 周波数判定の許容幅（Hz）

FREQ_MAP: dict[int, int] = {
    1: 18000,
    2: 18500,
    3: 19000,
    4: 19500,
}
# 逆引き用（受信側）
_CHOICE_BY_FREQ = {v: k for k, v in FREQ_MAP.items()}


def is_available() -> bool:
    """pyaudio と numpy が利用可能かどうかを返す。"""
    return _AVAILABLE


def _generate_tone(frequency: int, duration: float = TONE_DURATION) -> bytes:
    """指定周波数のサイン波を生成し、16bit PCM バイト列として返す。"""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    wave = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
    return wave.tobytes()


def _detect_choice(data: bytes) -> int | None:
    """PCM バイト列を FFT 解析し、対応する選択肢（1〜4）を返す。該当なしは None。"""
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / SAMPLE_RATE)

    peak_idx = int(np.argmax(spectrum))
    peak_freq = float(freqs[peak_idx])

    for choice_freq, choice in _CHOICE_BY_FREQ.items():
        if abs(peak_freq - choice_freq) <= FREQ_TOLERANCE:
            return choice
    return None


class AudioVoteNetwork:
    """Audio FSK による多数決送受信クラス。

    VoteNetwork (UDP) と同じインターフェースを持つ。
    pyaudio / numpy が未インストールの場合、start() / send_vote() は何もしない。
    """

    def __init__(self, on_update: Callable[[Counter], None]) -> None:
        self._on_update = on_update
        self._votes: Counter = Counter()
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None
        self._pa: "pyaudio.PyAudio | None" = None

    def start(self) -> None:
        if not _AVAILABLE:
            return
        self._pa = pyaudio.PyAudio()
        self._running = True
        self._thread = threading.Thread(target=self._listen, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def send_vote(self, choice: int) -> None:
        """指定した選択肢（1〜4）のトーンをスピーカーから送信し、ローカルにも集計する。"""
        if not _AVAILABLE or choice not in FREQ_MAP:
            return

        tone = _generate_tone(FREQ_MAP[choice])

        def _play() -> None:
            pa = pyaudio.PyAudio()
            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=SAMPLE_RATE,
                    output=True,
                )
                stream.write(tone)
                stream.stop_stream()
                stream.close()
            finally:
                pa.terminate()

        threading.Thread(target=_play, daemon=True).start()

        with self._lock:
            self._votes[choice] += 1
        self._on_update(Counter(self._votes))

    def reset(self) -> None:
        with self._lock:
            self._votes.clear()
        self._on_update(Counter())

    def _listen(self) -> None:
        """バックグラウンドでマイク入力を監視し、FFT で選択肢を検出する。"""
        if self._pa is None:
            return
        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=SAMPLE_RATE,
                input=True,
                frames_per_buffer=CHUNK_SIZE,
            )
        except Exception as e:
            print(f"[AudioVoteNetwork] マイクのオープンに失敗しました: {e}")
            return

        try:
            while self._running:
                try:
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                except OSError:
                    continue
                choice = _detect_choice(data)
                if choice is not None:
                    with self._lock:
                        self._votes[choice] += 1
                    self._on_update(Counter(self._votes))
        finally:
            stream.stop_stream()
            stream.close()
