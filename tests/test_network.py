"""Unit tests for core/network.py — socket はモック化して実ネットワーク通信を行わない。"""
import json
import socket
import threading
import unittest
from collections import Counter
from unittest.mock import MagicMock, patch, call


class TestVoteNetwork(unittest.TestCase):
    def _make_network(self, on_update=None):
        """socket をモックした VoteNetwork を返す。"""
        if on_update is None:
            on_update = MagicMock()

        mock_sock = MagicMock()
        mock_sock.recvfrom.side_effect = socket.timeout  # listen ループをすぐ抜けさせる

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        return net, mock_sock, on_update

    def setUp(self):
        # モジュールキャッシュをリセット (他テストの影響を受けない)
        import importlib, core.network
        importlib.reload(core.network)

    # ------------------------------------------------------------------
    def test_send_vote_broadcasts_json(self):
        """send_vote は question_id 付きの JSON ペイロードをブロードキャストアドレスへ送る。"""
        from core.network import BROADCAST_ADDR, BROADCAST_PORT
        net, mock_sock, on_update = self._make_network()

        net.send_vote(3)

        expected_payload = json.dumps({"type": "vote", "vote": 3, "question_id": 1}).encode()
        mock_sock.sendto.assert_called_once_with(
            expected_payload, (BROADCAST_ADDR, BROADCAST_PORT)
        )

    def test_send_vote_updates_local_counter(self):
        """send_vote はブロードキャスト送信に加え、ローカル _votes を即時加算する。"""
        on_update = MagicMock()
        net, mock_sock, _ = self._make_network(on_update=on_update)

        net.send_vote(1)

        self.assertEqual(net._votes[1], 1)
        on_update.assert_called_once()
        args, _ = on_update.call_args
        self.assertEqual(args[0][1], 1)

    def test_reset_clears_votes(self):
        """reset() で _votes がすべてクリアされる。"""
        net, mock_sock, on_update = self._make_network()
        net.send_vote(4)
        net.send_vote(4)

        net.reset()

        self.assertEqual(len(net._votes), 0)

    def test_reset_calls_on_update_with_empty_counter(self):
        """reset() 後、on_update が空の Counter で呼ばれる。"""
        on_update = MagicMock()
        net, mock_sock, _ = self._make_network(on_update=on_update)
        net.send_vote(2)
        on_update.reset_mock()

        net.reset()

        on_update.assert_called_once()
        args, _ = on_update.call_args
        self.assertEqual(len(args[0]), 0)

    def _run_listen_with_packets(self, net, mock_sock, packets):
        """指定パケット列を受信させて _listen() を同期実行するヘルパー。"""
        call_count = [0]

        def controlled_recvfrom(_size):
            call_count[0] += 1
            if call_count[0] <= len(packets):
                return packets[call_count[0] - 1]
            net._running = False
            raise socket.timeout

        mock_sock.recvfrom.side_effect = controlled_recvfrom
        net._running = True
        net._listen()

    def test_listen_processes_valid_packet(self):
        """_listen() が正常な JSON パケット（新フォーマット）を受け取ると _votes を更新する。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        valid_payload = json.dumps({"type": "vote", "vote": 3, "question_id": 1}).encode()
        self._run_listen_with_packets(net, mock_sock, [(valid_payload, ("192.168.1.2", 45678))])

        self.assertEqual(net._votes[3], 1)

    def test_listen_processes_legacy_packet(self):
        """_listen() が question_id なし旧フォーマットのパケットも受け付ける。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        legacy_payload = json.dumps({"vote": 2}).encode()
        self._run_listen_with_packets(net, mock_sock, [(legacy_payload, ("192.168.1.2", 45678))])

        self.assertEqual(net._votes[2], 1)

    def test_listen_ignores_vote_for_different_question(self):
        """_listen() が現在の問題と異なる question_id の票を無視する。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        net._current_question = 2
        wrong_q_payload = json.dumps({"type": "vote", "vote": 1, "question_id": 1}).encode()
        self._run_listen_with_packets(net, mock_sock, [(wrong_q_payload, ("192.168.1.2", 45678))])

        self.assertEqual(len(net._votes), 0)

    def test_listen_handles_question_message(self):
        """_listen() が question メッセージで問題番号を更新し投票をリセットする。"""
        on_update = MagicMock()
        on_question_changed = MagicMock()
        mock_sock = MagicMock()

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update, on_question_changed=on_question_changed)

        net._votes[1] = 3  # 既存の票
        q_payload = json.dumps({"type": "question", "question_id": 5}).encode()
        self._run_listen_with_packets(net, mock_sock, [(q_payload, ("192.168.1.2", 45678))])

        self.assertEqual(net._current_question, 5)
        self.assertEqual(len(net._votes), 0)
        on_question_changed.assert_called_once_with(5)

    def test_listen_ignores_invalid_json(self):
        """_listen() が壊れた JSON を受け取っても例外を握りつぶす。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        call_count = [0]

        def controlled_recvfrom(_size):
            call_count[0] += 1
            if call_count[0] == 1:
                return b"THIS IS NOT JSON", ("192.168.1.2", 45678)
            net._running = False
            raise socket.timeout  # ループ終了

        mock_sock.recvfrom.side_effect = controlled_recvfrom

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        net._running = True

        def run():
            net._listen()

        t = threading.Thread(target=run)
        t.start()
        t.join(timeout=2)

        # 票は加算されていない
        self.assertEqual(len(net._votes), 0)

    def test_listen_ignores_self_sent_packet(self):
        """_listen() は自分の IP から来たパケットを無視して二重加算を防ぐ。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        call_count = [0]
        local_ip = "192.168.1.10"

        def controlled_recvfrom(_size):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({"vote": 2}).encode(), (local_ip, 45678)
            net._running = False
            raise socket.timeout

        mock_sock.recvfrom.side_effect = controlled_recvfrom

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        net._local_ip = local_ip
        net._running = True
        on_update.reset_mock()
        net._listen()

        self.assertEqual(net._votes[2], 0)
        on_update.assert_not_called()

    def test_listen_ignores_out_of_range_vote(self):
        """_listen() が 1〜4 以外の vote 値を無視する。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        call_count = [0]

        def controlled_recvfrom(_size):
            call_count[0] += 1
            if call_count[0] == 1:
                return json.dumps({"vote": 99}).encode(), ("192.168.1.2", 45678)
            net._running = False
            raise socket.timeout

        mock_sock.recvfrom.side_effect = controlled_recvfrom

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        net._running = True
        net._listen()

        self.assertEqual(len(net._votes), 0)


if __name__ == "__main__":
    unittest.main()
