"""ggwave 超音波モードを用いたオフライン P2P 多数決モジュール。

送受信フォーマットは JSON 文字列の以下形式に固定する。
  {"q": 現在の問題番号, "c": 選択した番号}

- 送信: ggwave.encode() で超音波データを生成し、PyAudio で再生する
- 受信: マイク入力を ggwave.decode() へ渡して JSON を復元する
- UI へは「現在の問題番号」の票だけを Counter で通知する
"""

from __future__ import annotations

import json
import logging
import importlib
import os
import threading
import time
from collections import Counter
from typing import Callable

try:
    pyaudio = importlib.import_module("pyaudio")
    try:
        ggwave = importlib.import_module("ggwave")
        _BACKEND = "ggwave"
    except Exception:
        ggwave = importlib.import_module("pyggwave")
        _BACKEND = "pyggwave"
    _AVAILABLE = True
except Exception:
    ggwave = None
    pyaudio = None
    _BACKEND = "none"
    _AVAILABLE = False

logger = logging.getLogger(__name__)

# ggwave のデフォルトに寄せた設定（入力は int16 / 48kHz）
_SAMPLE_RATE = 48000
_CHUNK_SIZE = 1024

# Windows + pyggwave で ULTRASOUND_FASTEST を測定した際の主成分ピーク近似値
_ULTRASOUND_FASTEST_BASE_PEAK_HZ = 20000
_DEFAULT_TARGET_TX_HZ = 22000.0


def _clamp_tx_rate_multiplier(value: float) -> float:
    """送信レート倍率を安全範囲に丸める。"""
    return max(0.8, min(1.3, value))

def _read_tx_rate_multiplier() -> float:
    """送信時の再生レート倍率を環境変数から読み取る。"""
    override_multiplier = os.getenv("SHADOWANSWER_AUDIO_TX_RATE_MULTIPLIER")
    if override_multiplier is not None:
        try:
            return _clamp_tx_rate_multiplier(float(override_multiplier))
        except Exception:
            return 1.0

    raw_target_hz = os.getenv("SHADOWANSWER_AUDIO_TX_TARGET_HZ", str(_DEFAULT_TARGET_TX_HZ))
    try:
        target_hz = float(raw_target_hz)
    except Exception:
        target_hz = _DEFAULT_TARGET_TX_HZ

    if target_hz <= 0:
        return 1.0

    return _clamp_tx_rate_multiplier(target_hz / _ULTRASOUND_FASTEST_BASE_PEAK_HZ)


# 送信側の再生レート倍率。1.0より大きいと音は高くなるが、上げすぎると復号率が落ちる。
_TX_RATE_MULTIPLIER = _read_tx_rate_multiplier()

# 同一端末の送信を受信側で再加算しないための抑制秒数
_SELF_SUPPRESS_SEC = 0.9


def _resolve_ultrasound_protocol_id() -> int:
    """ggwave の超音波プロトコルIDを動的解決する。

    バージョン差で定数名が異なるため、候補を順に探索する。
    見つからない場合は既定値 1 へフォールバックする。
    """
    candidates = [
        "ULTRASOUND_FASTEST",
        "ULTRASOUND_FAST",
        "ULTRASOUND_NORMAL",
        "GGWAVE_PROTOCOL_ULTRASOUND_FASTEST",
        "GGWAVE_PROTOCOL_ULTRASOUND_FAST",
        "GGWAVE_PROTOCOL_ULTRASOUND_NORMAL",
        "GGWAVE_PROTOCOL_DT_ULTRASOUND",
    ]

    for protocol_ns in (getattr(ggwave, "ProtocolId", None), getattr(ggwave, "Protocol", None), ggwave):
        if protocol_ns is None:
            continue
        for name in candidates:
            value = getattr(protocol_ns, name, None)
            if value is not None:
                try:
                    return int(getattr(value, "value", value))
                except Exception:
                    pass

    # 互換性重視: 取得できない場合でも動作継続
    return 1


def _parse_vote_payload(raw_text: str) -> tuple[int, int] | None:
    """復号した文字列から (question_no, choice) を取り出す。"""
    try:
        payload = json.loads(raw_text)
        question_no = int(payload.get("q", 0))
        choice = int(payload.get("c", 0))
        if question_no <= 0:
            return None
        if choice not in (1, 2, 3, 4):
            return None
        return question_no, choice
    except Exception:
        return None


def _ggwave_init() -> object:
    """利用中バックエンドに応じてデコーダを初期化する。"""
    if hasattr(ggwave, "init"):
        return ggwave.init()
    return ggwave.raw__init()


def _ggwave_free(instance: object) -> None:
    """利用中バックエンドに応じてデコーダを解放する。"""
    if hasattr(ggwave, "free"):
        ggwave.free(instance)
        return
    if hasattr(ggwave, "raw__free"):
        ggwave.raw__free(instance)


def _ggwave_encode(payload_text: str, protocol_id: int) -> bytes:
    """利用中バックエンドに応じて送信用波形を生成する。"""
    if _BACKEND == "pyggwave":
        encode_instance: int | None = None
        try:
            if hasattr(ggwave, "raw__init"):
                encode_instance = ggwave.raw__init()

            if encode_instance is not None:
                return ggwave.raw__encode(
                    payload_text,
                    protocolId=protocol_id,
                    volume=35,
                    instance=encode_instance,
                )
            return ggwave.raw__encode(payload_text, protocolId=protocol_id, volume=35)
        finally:
            if encode_instance is not None and hasattr(ggwave, "raw__free"):
                try:
                    ggwave.raw__free(encode_instance)
                except Exception:
                    pass

    if hasattr(ggwave, "encode"):
        try:
            return ggwave.encode(payload_text, protocolId=protocol_id, volume=35)
        except Exception:
            # ggwave バージョン差分でキーワード引数が受け付けられない場合がある。
            for args in (
                (payload_text, protocol_id, 35),
                (payload_text, protocol_id),
                (payload_text,),
            ):
                try:
                    return ggwave.encode(*args)
                except Exception:
                    continue

    if hasattr(ggwave, "raw__encode"):
        return ggwave.raw__encode(payload_text, protocolId=protocol_id, volume=35)

    raise RuntimeError("ggwave encode 関数が見つかりません")


def _ggwave_decode(instance: object, data: bytes) -> bytes | None:
    """利用中バックエンドに応じて受信波形をデコードする。"""
    if hasattr(ggwave, "decode"):
        return ggwave.decode(instance, data)
    return ggwave.raw__decode(instance, data)


def _tx_format_and_frame_bytes() -> tuple[int, int]:
    """送信ストリームのPyAudioフォーマットと1サンプルバイト数を返す。"""
    if _BACKEND == "pyggwave":
        return pyaudio.paInt16, 2
    return pyaudio.paFloat32, 4


def is_available() -> bool:
    """ggwave と pyaudio が利用可能かどうかを返す。"""
    return _AVAILABLE


class AudioVoteNetwork:
    """ggwave 音波による多数決送受信クラス。"""

    def __init__(self, on_update: Callable[[Counter], None]) -> None:
        self._on_update = on_update
        self._lock = threading.Lock()

        # 問題番号ごとの票: { q: Counter({choice: count}) }
        self._votes_by_question: dict[int, Counter] = {}
        self._current_question: int = 1

        self._running = False
        self._thread: threading.Thread | None = None

        self._pa: object | None = None
        self._decoder: object | None = None

        self._protocol_id = _resolve_ultrasound_protocol_id() if _AVAILABLE else 1
        self._last_sent_at: float = 0.0

    def start(self) -> None:
        if not _AVAILABLE:
            logger.warning("AudioVoteNetwork: ggwave/pyaudio が未インストールのため無効化")
            return

        try:
            self._pa = pyaudio.PyAudio()
            self._decoder = _ggwave_init()
            self._running = True
            self._thread = threading.Thread(target=self._listen, daemon=True)
            self._thread.start()
        except Exception as e:
            logger.warning("AudioVoteNetwork: 初期化失敗: %s", e)
            self._running = False

    def stop(self) -> None:
        self._running = False

        if self._decoder is not None:
            try:
                _ggwave_free(self._decoder)
            except Exception:
                pass
            self._decoder = None

        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None

    def send_vote(self, choice: int) -> None:
        """現在の問題番号に対して選択肢を送信し、ローカル票にも反映する。"""
        if not _AVAILABLE:
            return
        if choice not in (1, 2, 3, 4):
            return

        with self._lock:
            question_no = self._current_question

        payload_text = json.dumps({"q": question_no, "c": choice}, separators=(",", ":"))

        try:
            waveform = _ggwave_encode(payload_text, self._protocol_id)
        except Exception as e:
            logger.warning("send_vote: encode 失敗: %s", e)
            waveform = b""

        if waveform:
            self._last_sent_at = time.monotonic()

            def _play() -> None:
                try:
                    pa = pyaudio.PyAudio()
                    tx_format, frame_bytes = _tx_format_and_frame_bytes()
                    stream = pa.open(
                        format=tx_format,
                        channels=1,
                        rate=int(_SAMPLE_RATE * _TX_RATE_MULTIPLIER),
                        output=True,
                    )
                    stream.write(waveform, num_frames=len(waveform) // frame_bytes)
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
                except Exception as e:
                    logger.warning("send_vote: 再生失敗: %s", e)

            threading.Thread(target=_play, daemon=True).start()

        with self._lock:
            votes = self._votes_by_question.setdefault(question_no, Counter())
            votes[choice] += 1
            current_votes = Counter(self._votes_by_question.get(self._current_question, Counter()))
        self._on_update(current_votes)

    def shift_question(self, delta: int) -> int:
        """現在の問題番号を増減し、現在問題の票を再通知する。"""
        if delta == 0:
            with self._lock:
                return self._current_question

        with self._lock:
            self._current_question = max(1, self._current_question + delta)
            new_question = self._current_question
            current_votes = Counter(self._votes_by_question.get(new_question, Counter()))

        self._on_update(current_votes)
        return new_question

    def get_current_question(self) -> int:
        with self._lock:
            return self._current_question

    def reset(self) -> None:
        with self._lock:
            self._votes_by_question.clear()
        self._on_update(Counter())

    def _listen(self) -> None:
        """バックグラウンドでマイク入力を監視し、復号結果を集計する。"""
        if self._pa is None or self._decoder is None:
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

        try:
            while self._running:
                try:
                    data = stream.read(_CHUNK_SIZE, exception_on_overflow=False)
                except Exception:
                    continue

                try:
                    decoded = _ggwave_decode(self._decoder, data)
                except Exception:
                    continue

                if not decoded:
                    continue

                try:
                    text = decoded.decode("utf-8", errors="ignore")
                except Exception:
                    continue

                parsed = _parse_vote_payload(text)
                if not parsed:
                    continue

                now = time.monotonic()
                if now - self._last_sent_at < _SELF_SUPPRESS_SEC:
                    continue

                question_no, choice = parsed
                with self._lock:
                    votes = self._votes_by_question.setdefault(question_no, Counter())
                    votes[choice] += 1
                    is_current = question_no == self._current_question
                    current_votes = Counter(self._votes_by_question.get(self._current_question, Counter()))

                if is_current:
                    self._on_update(current_votes)
        finally:
            try:
                stream.stop_stream()
                stream.close()
            except Exception:
                pass
