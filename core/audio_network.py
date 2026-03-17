"""高周波 Audio FSK を用いたオフライン P2P 多数決モジュール。

選択肢ごとに以下の周波数を使用:
  1: 18000 Hz
  2: 18500 Hz
  3: 19000 Hz
  4: 19500 Hz

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
    logger.info("is_available() called: _AVAILABLE=%s", _AVAILABLE)
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

    # 全体のピーク（デバッグ用: 低周波ノイズに引っ張られやすい）
    global_peak_idx = int(np.argmax(spectrum))
    global_peak_freq = float(freqs[global_peak_idx])
    global_peak_amp = float(spectrum[global_peak_idx])

    # 各ターゲット周波数でのスペクトル振幅をログ出力
    target_amps = {}
    for choice_freq in _CHOICE_BY_FREQ:
        idx = int(round(choice_freq / (SAMPLE_RATE / len(samples))))
        idx = max(0, min(idx, len(spectrum) - 1))
        target_amps[choice_freq] = float(spectrum[idx])

    logger.debug(
        "FFT global_peak=%.1f Hz (amp=%.1f) | target_amps=%s",
        global_peak_freq,
        global_peak_amp,
        {f"{f}Hz": f"{a:.1f}" for f, a in target_amps.items()},
    )

    peak_idx = int(np.argmax(spectrum))
    peak_freq = float(freqs[peak_idx])

    for choice_freq, choice in _CHOICE_BY_FREQ.items():
        if abs(peak_freq - choice_freq) <= FREQ_TOLERANCE:
            logger.info("DETECTED choice=%d (freq=%.1f Hz)", choice, peak_freq)
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
            logger.warning("AudioVoteNetwork: pyaudio/numpy が未インストールのため無効化")
            return
        self._pa = pyaudio.PyAudio()
        logger.info("AudioVoteNetwork: PyAudio 初期化完了 (デバイス数=%d)", self._pa.get_device_count())
        for i in range(self._pa.get_device_count()):
            info = self._pa.get_device_info_by_index(i)
            logger.info(
                "  device[%d]: name=%r in_ch=%d out_ch=%d sr=%s",
                i, info["name"], info["maxInputChannels"], info["maxOutputChannels"], info["defaultSampleRate"],
            )
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
        logger.info("send_vote: choice=%d freq=%d Hz tone_bytes=%d", choice, freq, len(tone))

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
                logger.info("send_vote: 再生完了 choice=%d", choice)
            except Exception as e:
                logger.error("send_vote: 再生エラー: %s", e)
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
            logger.info("_listen: マイクストリームオープン成功 (SAMPLE_RATE=%d, CHUNK_SIZE=%d)", SAMPLE_RATE, CHUNK_SIZE)
        except Exception as e:
            logger.error("_listen: マイクのオープンに失敗しました: %s", e)
            print(f"[AudioVoteNetwork] マイクのオープンに失敗しました: {e}")
            return

        # デバウンス: 1票検出後 DEBOUNCE_SEC 秒間は同じ選択肢を無視する
        DEBOUNCE_SEC = 0.8
        last_detected_at: dict[int, float] = {}

        chunk_count = 0
        try:
            while self._running:
                try:
                    data = stream.read(CHUNK_SIZE, exception_on_overflow=False)
                except OSError as e:
                    logger.warning("_listen: stream.read OSError: %s", e)
                    continue
                chunk_count += 1
                # 100チャンクごとに生存確認ログ（約9秒ごと）
                if chunk_count % 100 == 0:
                    logger.debug("_listen: 稼働中 chunk_count=%d", chunk_count)
                choice = _detect_choice(data)
                if choice is not None:
                    now = time.monotonic()
                    if now - last_detected_at.get(choice, 0.0) < DEBOUNCE_SEC:
                        logger.debug("_listen: デバウンスで無視 choice=%d", choice)
                        continue
                    last_detected_at[choice] = now
                    with self._lock:
                        self._votes[choice] += 1
                    logger.info("_listen: 投票カウント choice=%d votes=%s", choice, dict(self._votes))
                    self._on_update(Counter(self._votes))
        finally:
            stream.stop_stream()
            stream.close()
            logger.info("_listen: ストリームクローズ")
