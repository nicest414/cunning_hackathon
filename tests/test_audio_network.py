"""Unit tests for core/audio_network.py - ggwave/pyaudio はモック化する。"""

import importlib
import types
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch


class TestParseVotePayload(unittest.TestCase):
    def setUp(self):
        import core.audio_network
        importlib.reload(core.audio_network)

    def test_parse_valid_payload(self):
        """有効な q/c ペイロードを正しく復元できる。"""
        from core.audio_network import _parse_vote_payload

        self.assertEqual(_parse_vote_payload('{"q":2,"c":4}'), (2, 4))

    def test_parse_invalid_payload_returns_none(self):
        """不正ペイロードは None を返す。"""
        from core.audio_network import _parse_vote_payload

        self.assertIsNone(_parse_vote_payload('{"q":0,"c":1}'))
        self.assertIsNone(_parse_vote_payload('{"q":1,"c":9}'))
        self.assertIsNone(_parse_vote_payload('not-json'))


class TestAudioVoteNetwork(unittest.TestCase):
    def setUp(self):
        import core.audio_network
        importlib.reload(core.audio_network)

    def test_send_vote_encodes_qc_payload_and_updates_local_counter(self):
        """send_vote() が q/c 形式でエンコードし、ローカル票を更新する。"""
        on_update = MagicMock()

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.ggwave") as mock_ggwave, \
               patch("core.audio_network._BACKEND", "ggwave"), \
             patch("core.audio_network.pyaudio") as mock_pyaudio, \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_ggwave.encode.return_value = b"\x00" * 400
            mock_pyaudio.paFloat32 = 1
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(3)

        encoded_text = mock_ggwave.encode.call_args.args[0]
        self.assertEqual(encoded_text, '{"q":1,"c":3}')
        on_update.assert_called_once()
        votes = on_update.call_args.args[0]
        self.assertEqual(votes[3], 1)

    def test_send_vote_uses_raw_encode_when_encode_is_missing(self):
        """pyggwave 互換: encode が無い場合は raw__encode を使う。"""
        on_update = MagicMock()

        fake_protocol = types.SimpleNamespace(ULTRASOUND_FASTEST=types.SimpleNamespace(value=5))
        fake_ggwave = types.SimpleNamespace(
            Protocol=fake_protocol,
            raw__encode=MagicMock(return_value=b"\x00" * 100),
            raw__decode=MagicMock(return_value=None),
            raw__init=MagicMock(return_value=1),
            raw__free=MagicMock(),
        )

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.ggwave", fake_ggwave), \
             patch("core.audio_network._BACKEND", "pyggwave"), \
             patch("core.audio_network.pyaudio") as mock_pyaudio, \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_pyaudio.paInt16 = 8
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(4)

        fake_ggwave.raw__encode.assert_called_once()
        encoded_text = fake_ggwave.raw__encode.call_args.args[0]
        self.assertEqual(encoded_text, '{"q":1,"c":4}')

    def test_send_vote_falls_back_when_encode_signature_differs(self):
        """ggwave 互換: encode の実装差で失敗しても別シグネチャへフォールバックする。"""
        on_update = MagicMock()

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.ggwave") as mock_ggwave, \
             patch("core.audio_network._BACKEND", "ggwave"), \
             patch("core.audio_network.pyaudio") as mock_pyaudio, \
             patch("core.audio_network.threading.Thread") as mock_thread:
            mock_ggwave.encode.side_effect = [
                Exception("'dict' object has no attribute 'params'"),
                b"\x00" * 200,
            ]
            mock_pyaudio.paFloat32 = 1
            mock_thread.return_value = MagicMock()

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net.send_vote(2)

        self.assertEqual(mock_ggwave.encode.call_count, 2)
        # 1回目はキーワード引数、2回目は位置引数フォールバック
        self.assertEqual(mock_ggwave.encode.call_args_list[1].args[0], '{"q":1,"c":2}')
        on_update.assert_called_once()

    def test_shift_question_changes_current_question_and_emits_counter(self):
        """shift_question() で問題番号を変更し、対象問題の票を通知する。"""
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

    def test_listen_updates_current_question_votes_on_receive(self):
        """受信票が現在問題なら on_update が呼ばれる。"""
        on_update = MagicMock()

        with patch("core.audio_network._AVAILABLE", True), \
             patch("core.audio_network.ggwave") as mock_ggwave, \
             patch("core.audio_network.pyaudio") as mock_pyaudio:
            mock_pyaudio.paInt16 = 8
            mock_pa = MagicMock()
            mock_stream = MagicMock()
            mock_pa.open.return_value = mock_stream
            mock_pyaudio.PyAudio.return_value = mock_pa

            # 1回だけPCMを返し、その次でループを終える
            calls = {"n": 0}

            def _read(*args, **kwargs):
                calls["n"] += 1
                if calls["n"] == 1:
                    return b"pcm"
                net._running = False
                raise Exception("stop")

            mock_stream.read.side_effect = _read
            mock_ggwave.decode.side_effect = [b'{"q":1,"c":2}']

            from core.audio_network import AudioVoteNetwork
            net = AudioVoteNetwork(on_update=on_update)
            net._pa = mock_pa
            net._decoder = object()
            net._running = True
            net._listen()

        on_update.assert_called_once()
        emitted = on_update.call_args.args[0]
        self.assertEqual(emitted[2], 1)


if __name__ == "__main__":
    unittest.main()
