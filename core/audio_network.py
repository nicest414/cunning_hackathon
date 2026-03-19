"""固定周波数トーンによる高周波数 P2P 多数決モジュール。

6 つの固定周波数を信号に割り当てる:
  選択肢 1 : 17000 Hz
  選択肢 2 : 17500 Hz
  選択肢 3 : 18000 Hz
  選択肢 4 : 18500 Hz
  前の問題 : 19000 Hz  (ホストのみ送信)
  次の問題 : 19500 Hz  (ホストのみ送信)

送信: numpy で正弦波を生成し PyAudio で再生する
受信: マイク入力に FFT をかけて帯域内のピーク周波数を検出する
"""

from __future__ import annotations

import importlib
import logging
import threading
import time
from collections import Counter
from typing import Callable

try:
    import numpy as np
    pyaudio = importlib.import_module("pyaudio")
    _AVAILABLE = True
except Exception:
    np = None  # type: ignore[assignment]
    pyaudio = None
    _AVAILABLE = False

logger = logging.getLogger(__name__)

_SAMPLE_RATE = 48000

# 送信トーンの長さ [秒]
_TONE_DURATION_SEC = 0.35

# FFT ウィンドウサイズ [サンプル数] — 約 170 ms @ 48 kHz, 周波数分解能 ≈ 5.9 Hz/bin
_FFT_WINDOW_SIZE = 8192

# 周波数検出の許容誤差 [Hz]
_FREQ_TOLERANCE_HZ = 180

# ピーク / 帯域平均の比率閾値（これを超えたときのみ信号とみなす）
_SNR_THRESHOLD = 8.0

# 同一信号の再検出抑制時間 [秒]
_DEBOUNCE_SEC = 1.2

# 自己送信後のマイク抑制時間 [秒]
_SELF_SUPPRESS_SEC = 0.8

# stream.read 連続失敗時の制御値
_READ_FAILURE_LIMIT = 10
_READ_FAILURE_SLEEP_SEC = 0.05

_CHUNK_SIZE = 1024

# ─── 6 つの信号周波数 ───────────────────────────────────────────────────────
FREQ_VOTE_1 = 17000
FREQ_VOTE_2 = 17500
FREQ_VOTE_3 = 18000
FREQ_VOTE_4 = 18500
FREQ_QUESTION_PREV = 19000  # 前の問題へ (ホストのみ送信)
FREQ_QUESTION_NEXT = 19500  # 次の問題へ (ホストのみ送信)

_SIGNAL_FREQS: tuple[int, ...] = (
    FREQ_VOTE_1,
    FREQ_VOTE_2,
    FREQ_VOTE_3,
    FREQ_VOTE_4,
    FREQ_QUESTION_PREV,
    FREQ_QUESTION_NEXT,
)

# 周波数 → 選択肢番号 (投票信号のみ)
_FREQ_TO_CHOICE: dict[int, int] = {
    FREQ_VOTE_1: 1,
    FREQ_VOTE_2: 2,
    FREQ_VOTE_3: 3,
    FREQ_VOTE_4: 4,
}


def is_available() -> bool:
    """numpy と pyaudio が利用可能かどうかを返す。"""
    return _AVAILABLE


def _generate_tone(frequency: float) -> bytes:
    """指定周波数の正弦波を int16 バイト列で生成する。
    フェードイン・アウト (10 ms) でクリックノイズを防ぐ。
    """
    n = int(_SAMPLE_RATE * _TONE_DURATION_SEC)
    t = np.linspace(0.0, _TONE_DURATION_SEC, n, endpoint=False)
    wave = np.sin(2.0 * np.pi * frequency * t)
    fade = int(_SAMPLE_RATE * 0.01)
    wave[:fade] *= np.linspace(0.0, 1.0, fade)
    wave[-fade:] *= np.linspace(1.0, 0.0, fade)
    return (wave * 32767).astype(np.int16).tobytes()


def _detect_signal(samples: "np.ndarray") -> int | None:
    """FFT でサンプル配列から信号周波数を検出する。

    16〜20.5 kHz の帯域内で最も強いピークが 6 つの既定周波数のいずれかと
    一致し、かつ SNR が閾値を超える場合にその周波数を返す。
    """
    fft_mag = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), d=1.0 / _SAMPLE_RATE)

    band_mask = (freqs >= 16000) & (freqs <= 20500)
    band_mag = fft_mag[band_mask]
    band_freqs = freqs[band_mask]

    if len(band_mag) == 0:
        return None

    peak_idx = int(np.argmax(band_mag))
    peak_freq = float(band_freqs[peak_idx])
    peak_mag = float(band_mag[peak_idx])

    mean_mag = float(np.mean(band_mag))
    if mean_mag == 0.0 or peak_mag / mean_mag < _SNR_THRESHOLD:
        return None

    for sig_freq in _SIGNAL_FREQS:
        if abs(peak_freq - sig_freq) <= _FREQ_TOLERANCE_HZ:
            return sig_freq

    return None


class AudioVoteNetwork:
    """固定周波数トーンによる多数決送受信クラス。"""

    def __init__(
        self,
        on_update: Callable[[Counter], None],
        on_question_changed: Callable[[int], None] | None = None,
        is_host: bool = False,
    ) -> None:
        self._on_update = on_update
        self._on_question_changed = on_question_changed
        self._is_host = is_host
        self._lock = threading.Lock()

        # 問題番号ごとの票: { q: Counter({choice: count}) }
        self._votes_by_question: dict[int, Counter] = {}
        self._current_question: int = 1

        self._running = False
        self._thread: threading.Thread | None = None
        self._pa: object | None = None

        self._last_sent_at: float = 0.0
        # 周波数ごとの最終検出時刻 (デバウンス用)
        self._last_detected: dict[int, float] = {}

    def start(self) -> None:
        if not _AVAILABLE:
            logger.warning("AudioVoteNetwork: numpy/pyaudio が未インストールのため無効化")
            return
        try:
            self._pa = pyaudio.PyAudio()
            self._running = True
            self._thread = threading.Thread(target=self._listen, daemon=True)
            self._thread.start()
        except Exception as e:
            logger.warning("AudioVoteNetwork: 初期化失敗: %s", e)
            self._running = False

    def stop(self) -> None:
        self._running = False
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def send_vote(self, choice: int) -> None:
        """選択肢 (1〜4) に対応するトーンを再生し、ローカル票にも反映する。"""
        if not _AVAILABLE or choice not in (1, 2, 3, 4):
            return

        freq_map = {1: FREQ_VOTE_1, 2: FREQ_VOTE_2, 3: FREQ_VOTE_3, 4: FREQ_VOTE_4}
        self._play_tone_async(freq_map[choice])

        with self._lock:
            question_no = self._current_question
            votes = self._votes_by_question.setdefault(question_no, Counter())
            votes[choice] += 1
            current_votes = Counter(votes)
        self._on_update(current_votes)

    def send_question(self, question_id: int) -> None:
        """互換インターフェース。音声では問題番号は送信しない (shift_question で代替)。"""
        pass

    def shift_question(self, delta: int) -> int:
        """問題番号を増減する。ホストの場合は方向トーンも再生する。"""
        if delta == 0:
            with self._lock:
                return self._current_question

        with self._lock:
            self._current_question = max(1, self._current_question + delta)
            new_question = self._current_question
            current_votes = Counter(self._votes_by_question.get(new_question, Counter()))

        self._on_update(current_votes)

        if self._is_host and _AVAILABLE:
            freq = FREQ_QUESTION_NEXT if delta > 0 else FREQ_QUESTION_PREV
            self._play_tone_async(freq)

        return new_question

    def get_current_question(self) -> int:
        with self._lock:
            return self._current_question

    def reset(self) -> None:
        with self._lock:
            self._votes_by_question.clear()
        self._on_update(Counter())

    # ─── 内部メソッド ──────────────────────────────────────────────────────

    def _play_tone_async(self, frequency: int) -> None:
        """指定周波数のトーンを別スレッドで再生する。"""
        waveform = _generate_tone(frequency)
        self._last_sent_at = time.monotonic()

        def _play() -> None:
            try:
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=_SAMPLE_RATE,
                    output=True,
                )
                stream.write(waveform, num_frames=len(waveform) // 2)
                stream.stop_stream()
                stream.close()
                pa.terminate()
            except Exception as e:
                logger.warning("_play_tone_async: 再生失敗: %s", e)

        threading.Thread(target=_play, daemon=True).start()

    def _listen(self) -> None:
        """バックグラウンドでマイク入力を監視し、FFT で信号を検出する。"""
        if self._pa is None:
            return

        try:
            stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=_SAMPLE_RATE,
                input=True,
                frames_per_buffer=_CHUNK_SIZE,
            )
        except Exception as e:
            logger.warning("_listen: マイクオープン失敗: %s", e)
            return

        buffer = np.array([], dtype=np.int16)
        read_failure_count = 0

        try:
            while self._running:
                try:
                    data = stream.read(_CHUNK_SIZE, exception_on_overflow=False)
                    read_failure_count = 0
                except Exception as e:
                    read_failure_count += 1
                    if read_failure_count == 1:
                        logger.warning("_listen: stream.read 失敗: %s", e)
                    if read_failure_count >= _READ_FAILURE_LIMIT:
                        logger.warning("_listen: 連続失敗のためリスニングを終了します")
                        break
                    time.sleep(_READ_FAILURE_SLEEP_SEC)
                    continue

                chunk = np.frombuffer(data, dtype=np.int16)
                buffer = np.concatenate([buffer, chunk])

                if len(buffer) < _FFT_WINDOW_SIZE:
                    continue

                window = buffer[:_FFT_WINDOW_SIZE].astype(np.float32)
                # 50% オーバーラップでスライド
                buffer = buffer[_FFT_WINDOW_SIZE // 2:]

                now = time.monotonic()
                if now - self._last_sent_at < _SELF_SUPPRESS_SEC:
                    continue

                detected_freq = _detect_signal(window)
                if detected_freq is None:
                    continue

                last = self._last_detected.get(detected_freq, 0.0)
                if now - last < _DEBOUNCE_SEC:
                    continue
                self._last_detected[detected_freq] = now

                self._handle_detected(detected_freq)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass

    def _handle_detected(self, freq: int) -> None:
        """検出した周波数に応じてコールバックを呼ぶ。"""
        choice = _FREQ_TO_CHOICE.get(freq)
        if choice is not None:
            with self._lock:
                question_no = self._current_question
                votes = self._votes_by_question.setdefault(question_no, Counter())
                votes[choice] += 1
                current_votes = Counter(votes)
            self._on_update(current_votes)
            return

        if freq == FREQ_QUESTION_PREV:
            delta = -1
        elif freq == FREQ_QUESTION_NEXT:
            delta = 1
        else:
            return

        with self._lock:
            self._current_question = max(1, self._current_question + delta)
            new_question = self._current_question
            current_votes = Counter(self._votes_by_question.get(new_question, Counter()))

        self._on_update(current_votes)
        if self._on_question_changed:
            self._on_question_changed(new_question)
