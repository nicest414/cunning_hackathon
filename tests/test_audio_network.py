"""Unit tests for core/audio_network.py — pyaudio をモックして実デバイスを使わない。"""
import importlib
import threading
import time
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch

import numpy as np


def _make_pcm(frequency: int, duration: float = 0.1, sample_rate: int = 44100) -> bytes:
    """テスト用: 指定周波数の純粋なサイン波 PCM バイト列を生成する。"""
    t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
    wave = (np.sin(2 * np.pi * frequency * t) * 32767).astype(np.int16)
    return wave.tobytes()


def _make_silence(duration: float = 0.1, sample_rate: int = 44100) -> bytes:
    """テスト用: 無音 PCM バイト列を生成する。"""
    n = int(sample_rate * duration)
    return (np.zeros(n, dtype=np.int16)).tobytes()


class TestDetectChoice(unittest.TestCase):
    def setUp(self):
        import importlib
        import core.audio_network
        importlib.reload(core.audio_network)

    def test_detect_known_frequency_returns_correct_choice(self):
        """各 FREQ_MAP の周波数トーンを与えると対応する選択肢が返る。"""
        from core.audio_network import _detect_choice, FREQ_MAP, CHUNK_SIZE, SAMPLE_RATE

        for choice, freq in FREQ_MAP.items():
            # CHUNK_SIZE サンプル分の純音を生成
            duration = CHUNK_SIZE / SAMPLE_RATE
            pcm = _make_pcm(freq, duration=duration, sample_rate=SAMPLE_RATE)
            result = _detect_choice(pcm)
            self.assertEqual(
                result, choice,
                f"freq={freq}Hz の純音で choice={choice} が検出されるべきだが {result} が返った",
            )

    def test_detect_silence_returns_none(self):
        """無音入力では None を返す（ZeroDivisionError も起きない）。"""
        from core.audio_network import _detect_choice, CHUNK_SIZE, SAMPLE_RATE

        duration = CHUNK_SIZE / SAMPLE_RATE
        pcm = _make_silence(duration=duration, sample_rate=SAMPLE_RATE)
        result = _detect_choice(pcm)
        self.assertIsNone(result)

    def test_detect_low_freq_noise_returns_none(self):
        """低周波ノイズ（例: 500 Hz）では None を返す（誤検出しない）。"""
        from core.audio_network import _detect_choice, CHUNK_SIZE, SAMPLE_RATE

        duration = CHUNK_SIZE / SAMPLE_RATE
        pcm = _make_pcm(500, duration=duration, sample_rate=SAMPLE_RATE)
        result = _detect_choice(pcm)
        self.assertIsNone(result)

    def test_noise_floor_zero_does_not_raise(self):
        """noise_floor が 0 になりうる無音入力でも ZeroDivisionError が起きない。"""
        from core.audio_network import _detect_choice

        # 完全ゼロバイト（all-zero samples）
        pcm = bytes(4096 * 2)  # 4096 int16 samples
        try:
            _detect_choice(pcm)
        except ZeroDivisionError:
            self.fail("_detect_choice() が ZeroDivisionError を送出した")


class TestAudioVoteNetwork(unittest.TestCase):
    def _make_network(self, on_update=None):
        """pyaudio をモックした AudioVoteNetwork を返す。"""
        if on_update is None:
            on_update = MagicMock()

        mock_pa = MagicMock()
        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio") as mock_pyaudio:
            mock_pyaudio.PyAudio.return_value = mock_pa
            mock_pyaudio.paInt16 = 8  # 実 pyaudio の定数と同値
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)

        return net, mock_pa, on_update

    def setUp(self):
        import core.audio_network
        importlib.reload(core.audio_network)

    def test_send_vote_updates_local_counter(self):
        """send_vote はローカルの _votes をすぐに加算し on_update を呼ぶ。"""
        on_update = MagicMock()

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio") as mock_pyaudio, \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            mock_pyaudio.paInt16 = 8
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(2)

        self.assertEqual(net._votes[2], 1)
        on_update.assert_called_once()
        args, _ = on_update.call_args
        self.assertEqual(args[0][2], 1)

    def test_send_vote_records_last_sent_at(self):
        """send_vote 後、_last_sent_at に対象 choice の時刻が記録される。"""
        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio") as mock_pyaudio, \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            mock_pyaudio.paInt16 = 8
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=MagicMock())
            before = time.monotonic()
            net.send_vote(3)
            after = time.monotonic()

        self.assertIn(3, net._last_sent_at)
        self.assertGreaterEqual(net._last_sent_at[3], before)
        self.assertLessEqual(net._last_sent_at[3], after)

    def test_self_loopback_suppression_in_listen(self):
        """_listen() は送信直後（DEBOUNCE_SEC 内）に同一 choice を検出しても集計しない。"""
        from core.audio_network import FREQ_MAP, CHUNK_SIZE, SAMPLE_RATE

        on_update = MagicMock()
        call_count = [0]

        # choice=1 (17000Hz) のチャンク PCM を生成
        duration = CHUNK_SIZE / SAMPLE_RATE
        tone_pcm = _make_pcm(FREQ_MAP[1], duration=duration, sample_rate=SAMPLE_RATE)

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio") as mock_pyaudio:
            mock_pyaudio.paInt16 = 8
            mock_pa = MagicMock()
            mock_pyaudio.PyAudio.return_value = mock_pa

            def controlled_read(_size, **kw):
                call_count[0] += 1
                if call_count[0] == 1:
                    return tone_pcm
                net._running = False
                raise OSError("eof")

            mock_stream = MagicMock()
            mock_stream.read.side_effect = controlled_read
            mock_pa.open.return_value = mock_stream

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)

        # send_vote で _last_sent_at を "今" に設定してから _listen を呼ぶ
        net._last_sent_at[1] = time.monotonic()
        net._running = True
        net._pa = mock_pa
        net._listen()

        # ループバック抑制により votes は 0 のまま
        self.assertEqual(net._votes[1], 0)

    def test_reset_clears_votes(self):
        """reset() で _votes がクリアされ on_update が空 Counter で呼ばれる。"""
        on_update = MagicMock()
        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio") as mock_pyaudio, \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()
            mock_pyaudio.paInt16 = 8
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(1)
            on_update.reset_mock()
            net.reset()

        self.assertEqual(len(net._votes), 0)
        on_update.assert_called_once()
        args, _ = on_update.call_args
        self.assertEqual(len(args[0]), 0)


if __name__ == "__main__":
    unittest.main()
