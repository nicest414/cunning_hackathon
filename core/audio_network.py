"""高周波 Audio FSK を用いたオフライン P2P 多数決モジュール。

選択肢ごとに以下の周波数を使用:
  1: 17000 Hz
  2: 17500 Hz
  3: 18000 Hz
  4: 18500 Hz

送信: numpy でサイン波を生成し pyaudio でスピーカーから再生。
受信: pyaudio でマイク入力を常時監視し、FFT でピーク周波数を検出。
"""

import logging
import threading
import time
from collections import Counter
from typing import Callable

try:
    import numpy as np
    import pyaudio
    _AVAILABLE = True
except ImportError:
    _AVAILABLE = False

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s][%(name)s][%(levelname)s] %(message)s",
)

SAMPLE_RATE = 44100
TONE_DURATION = 0.05       # 送信トーン長（秒）
CHUNK_SIZE = 4096          # 受信チャンクサイズ（サンプル数）
FREQ_TOLERANCE = 200       # 周波数判定の許容幅（Hz）
SNR_THRESHOLD = 10.0       # ノイズフロア比: この倍数を超えた場合のみ検出

FREQ_MAP: dict[int, int] = {
    1: 17000,
    2: 17500,
    3: 18000,
    4: 18500,
}
# 逆引き用（受信側）
_CHOICE_BY_FREQ = {v: k for k, v in FREQ_MAP.items()}


def is_available() -> bool:
    """pyaudio と numpy が利用可能かどうかを返す。"""
    return _AVAILABLE


def _generate_tone(frequency: int, duration: float = TONE_DURATION) -> bytes:
    """指定周波数のサイン波を生成し、16bit PCM バイト列として返す。"""
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    sine = np.sin(2 * np.pi * frequency * t)
    # 冒頭・末尾 5ms にフェードイン/フェードアウトを掛けてクリックノイズを抑制
    fade_samples = min(int(SAMPLE_RATE * 0.005), len(t) // 2)
    envelope = np.ones(len(t))
    envelope[:fade_samples] = np.linspace(0.0, 1.0, fade_samples)
    envelope[-fade_samples:] = np.linspace(1.0, 0.0, fade_samples)
    wave = (sine * envelope * 32767).astype(np.int16)
    return wave.tobytes()


def _detect_choice(data: bytes) -> int | None:
    """PCM バイト列を FFT 解析し、対応する選択肢（1〜4）を返す。該当なしは None。

    グローバルピーク（低周波ノイズが支配的）を使わず、
    各ターゲット周波数帯のSNRで判定する。
    """
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
    spectrum = np.abs(np.fft.rfft(samples))

    bin_width = SAMPLE_RATE / len(samples)

    # ノイズフロア: 中央値（低周波ノイズの大きなピークに引っ張られない）
    # 無音入力などで 0 になると SNR 計算で ZeroDivisionError が起きるため下限を設ける
    noise_floor = max(float(np.median(spectrum)), 1e-6)

    # 各ターゲット周波数の振幅を ±FREQ_TOLERANCE 窓内の最大値で取得
    target_amps: dict[int, float] = {}
    for choice_freq in _CHOICE_BY_FREQ:
        lo = int(max(0, (choice_freq - FREQ_TOLERANCE) / bin_width))
        hi = int(min(len(spectrum) - 1, (choice_freq + FREQ_TOLERANCE) / bin_width)) + 1
        target_amps[choice_freq] = float(np.max(spectrum[lo:hi]))

    # SNR閾値を超えた中で最も振幅が大きいものを選択
    threshold = noise_floor * SNR_THRESHOLD
    best_choice: int | None = None
    best_amp = threshold
    for choice_freq, choice in _CHOICE_BY_FREQ.items():
        amp = target_amps[choice_freq]
        if amp > best_amp:
            best_amp = amp
            best_choice = choice

    if best_choice is not None:
        logger.info(
            "DETECTED choice=%d (amp=%.1f, snr=%.1fx)",
            best_choice, best_amp, best_amp / noise_floor,
        )
    return best_choice


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
        # 自己ループバック抑制: send_vote した選択肢の送信時刻を記録
        self._last_sent_at: dict[int, float] = {}

    def start(self) -> None:
        if not _AVAILABLE:
            logger.warning("AudioVoteNetwork: pyaudio/numpy が未インストールのため無効化")
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
            logger.warning("send_vote: 無効 (available=%s, choice=%d)", _AVAILABLE, choice)
            return

        freq = FREQ_MAP[choice]
        tone = _generate_tone(freq)

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
            except Exception as e:
                logger.error("send_vote: 再生エラー: %s", e)
            finally:
                pa.terminate()

        with self._lock:
            self._last_sent_at[choice] = time.monotonic()
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
            logger.info("_listen: マイクストリームオープン成功 (SAMPLE_RATE=%d, CHUNK_SIZE=%d)", SAMPLE_RATE, CHUNK_SIZE)
        except Exception as e:
            logger.error("_listen: マイクのオープンに失敗しました: %s", e)
            print(f"[AudioVoteNetwork] マイクのオープンに失敗しました: {e}")
            return

        # デバウンス兼自己ループバック抑制: 検出または送信から DEBOUNCE_SEC 秒間は同じ選択肢を無視する
        DEBOUNCE_SEC = 0.8
        last_accepted_at: dict[int, float] = {}
        read_failure_count: int = 0

        try:
            while self._running:
                try:
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                    # 読み取りに成功したら連続失敗カウンタをリセット
                    read_failure_count = 0
                except Exception as e:
                    # 恒常的な read 失敗時の高速スピンを防ぐ
                    read_failure_count += 1
                    if read_failure_count == 1:
                        logger.warning("_listen: stream.read 失敗 (継続監視): %s", e)
                    if read_failure_count >= 10:
                        logger.warning("_listen: stream.read 連続失敗のためリスニングを終了します")
                        break
                    time.sleep(0.05)
                    continue
                choice = _detect_choice(data)
                if choice is not None:
                    now = time.monotonic()
                    with self._lock:
                        sent_at = self._last_sent_at.get(choice, 0.0)
                    last = max(last_accepted_at.get(choice, 0.0), sent_at)
                    if now - last < DEBOUNCE_SEC:
                        continue
                    last_accepted_at[choice] = now
                    with self._lock:
                        self._votes[choice] += 1
                    logger.info("audio vote: choice=%d votes=%s", choice, dict(self._votes))
                    self._on_update(Counter(self._votes))
        finally:
            stream.stop_stream()
            stream.close()
