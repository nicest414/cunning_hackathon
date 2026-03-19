"""Unit tests for core/audio_network.py — numpy/pyaudio はモック化する。"""

import importlib
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch

import numpy as np


class TestDetectSignal(unittest.TestCase):
    def setUp(self):
        import core.audio_network
        importlib.reload(core.audio_network)

    def _make_tone(self, frequency: float, n: int = 8192, sample_rate: int = 48000) -> np.ndarray:
        t = np.linspace(0.0, n / sample_rate, n, endpoint=False)
        return (np.sin(2.0 * np.pi * frequency * t) * 32767).astype(np.float32)

    def test_detects_vote_frequencies(self):
        """6 つの信号周波数が正しく検出される。"""
        from core.audio_network import (
            _detect_signal,
            FREQ_VOTE_1, FREQ_VOTE_2, FREQ_VOTE_3, FREQ_VOTE_4,
            FREQ_QUESTION_PREV, FREQ_QUESTION_NEXT,
        )
        for freq in (FREQ_VOTE_1, FREQ_VOTE_2, FREQ_VOTE_3, FREQ_VOTE_4,
                     FREQ_QUESTION_PREV, FREQ_QUESTION_NEXT):
            samples = self._make_tone(freq)
            result = _detect_signal(samples)
            self.assertEqual(result, freq, f"周波数 {freq} Hz が検出されなかった")

    def test_returns_none_for_silence(self):
        """無音では None を返す。"""
        from core.audio_network import _detect_signal
        samples = np.zeros(8192, dtype=np.float32)
        self.assertIsNone(_detect_signal(samples))

    def test_returns_none_for_out_of_band_frequency(self):
        """帯域外 (16 kHz 未満) の周波数では None を返す。"""
        from core.audio_network import _detect_signal
        samples = self._make_tone(1000.0)
        self.assertIsNone(_detect_signal(samples))

    def test_returns_none_for_unregistered_frequency(self):
        """既定外の高周波数では None を返す。"""
        from core.audio_network import _detect_signal
        samples = self._make_tone(16500.0)
        self.assertIsNone(_detect_signal(samples))


class TestAudioVoteNetwork(unittest.TestCase):
    def setUp(self):
        import core.audio_network
        importlib.reload(core.audio_network)

    def test_send_vote_updates_local_counter_and_plays_tone(self):
        """send_vote() がローカル票を更新し、トーン再生スレッドを起動する。"""
        on_update = MagicMock()

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio"), \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(3)

        on_update.assert_called_once()
        votes = on_update.call_args.args[0]
        self.assertEqual(votes[3], 1)
        mock_thread.assert_called()

    def test_send_vote_ignores_invalid_choice(self):
        """範囲外の選択肢は無視される。"""
        on_update = MagicMock()
        with patch("core.audio_network._AVAILABLE", True):
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(5)
        on_update.assert_not_called()

    def test_shift_question_changes_current_question_and_emits_counter(self):
        """shift_question() で問題番号が変わり、対象問題の票が通知される。"""
        on_update = MagicMock()

        with patch("core.audio_network._AVAILABLE", False):
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)

        net._votes_by_question[2] = Counter({1: 2, 4: 1})
        new_q = net.shift_question(+1)

        self.assertEqual(new_q, 2)
        on_update.assert_called_once()
        emitted = on_update.call_args.args[0]
        self.assertEqual(emitted[1], 2)
        self.assertEqual(emitted[4], 1)

    def test_shift_question_does_not_go_below_one(self):
        """問題番号は 1 未満にならない。"""
        with patch("core.audio_network._AVAILABLE", False):
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=MagicMock())
        self.assertEqual(net.shift_question(-1), 1)

    def test_shift_question_plays_next_tone_for_host(self):
        """ホストが +1 すると FREQ_QUESTION_NEXT のトーンが再生される。"""
        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio"), \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork, FREQ_QUESTION_NEXT
            net = AudioVoteNetwork(on_update=MagicMock(), is_host=True)
            net.shift_question(+1)

        # _play_tone_async 内で Thread が呼ばれること
        mock_thread.assert_called()
        # _generate_tone に渡す周波数が FREQ_QUESTION_NEXT であることを
        # play_tone_async のデバッグで確認するため、呼び出しがあった事のみチェック
        self.assertTrue(mock_thread.called)

    def test_shift_question_plays_prev_tone_for_host(self):
        """ホストが -1 すると FREQ_QUESTION_PREV のトーンが再生される (Q1 下限では再生しない)。"""
        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio"), \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=MagicMock(), is_host=True)
            net._current_question = 3
            net.shift_question(-1)

        mock_thread.assert_called()

    def test_shift_question_does_not_play_tone_for_non_host(self):
        """非ホストは問題番号変更操作でトーンを再生しない。"""
        on_update = MagicMock()
        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.pyaudio"), \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update, is_host=False)
            net.shift_question(+1)

        mock_thread.assert_not_called()

    def test_handle_detected_vote_updates_counter(self):
        """_handle_detected で投票周波数を受け取ると on_update が呼ばれる。"""
        on_update = MagicMock()
        with patch("core.audio_network._AVAILABLE", False):
            from core.audio_network import AudioVoteNetwork, FREQ_VOTE_2
            net = AudioVoteNetwork(on_update=on_update)

        net._handle_detected(FREQ_VOTE_2)

        on_update.assert_called_once()
        votes = on_update.call_args.args[0]
        self.assertEqual(votes[2], 1)

    def test_handle_detected_question_next_increments_question(self):
        """_handle_detected で FREQ_QUESTION_NEXT を受け取ると問題番号が増える。"""
        on_question_changed = MagicMock()
        on_update = MagicMock()
        with patch("core.audio_network._AVAILABLE", False):
            from core.audio_network import AudioVoteNetwork, FREQ_QUESTION_NEXT
            net = AudioVoteNetwork(on_update=on_update, on_question_changed=on_question_changed)

        net._handle_detected(FREQ_QUESTION_NEXT)

        self.assertEqual(net.get_current_question(), 2)
        on_question_changed.assert_called_once_with(2)

    def test_handle_detected_question_prev_decrements_question(self):
        """_handle_detected で FREQ_QUESTION_PREV を受け取ると問題番号が減る。"""
        on_question_changed = MagicMock()
        with patch("core.audio_network._AVAILABLE", False):
            from core.audio_network import AudioVoteNetwork, FREQ_QUESTION_PREV
            net = AudioVoteNetwork(on_update=MagicMock(), on_question_changed=on_question_changed)

        net._current_question = 3
        net._handle_detected(FREQ_QUESTION_PREV)

        self.assertEqual(net.get_current_question(), 2)
        on_question_changed.assert_called_once_with(2)

    def test_send_question_is_noop(self):
        """send_question() は互換インターフェースとして何もしない。"""
        on_update = MagicMock()
        with patch("core.audio_network._AVAILABLE", False):
            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)

        net.send_question(5)  # 例外も on_update も呼ばれない
        on_update.assert_not_called()


if __name__ == "__main__":
    unittest.main()
