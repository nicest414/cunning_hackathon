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
        """send_vote は JSON ペイロードをブロードキャストアドレスへ送る。"""
        from core.network import BROADCAST_ADDR, BROADCAST_PORT
        net, mock_sock, on_update = self._make_network()

        net.send_vote(3)

        expected_payload = json.dumps({"vote": 3}).encode()
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

    def test_listen_processes_valid_packet(self):
        """_listen() が正常な JSON パケットを受け取ると _votes を更新する。"""
        on_update = MagicMock()
        mock_sock = MagicMock()

        # 1パケット受信後に timeout を投げてループを終わらせる
        valid_payload = json.dumps({"vote": 3}).encode()
        mock_sock.recvfrom.side_effect = [
            (valid_payload, ("192.168.1.2", 45678)),
            socket.timeout,
        ]

        with patch("socket.socket", return_value=mock_sock):
            from core.network import VoteNetwork
            net = VoteNetwork(on_update=on_update)

        net._running = True
        # _listen を直接呼んでシミュレート (スレッドを使わない)
        # recvfrom が timeout を投げた時点でループが抜けるよう _running=False にする
        def stop_after(*args, **kwargs):
            net._running = False
            raise socket.timeout

        mock_sock.recvfrom.side_effect = [
            (valid_payload, ("192.168.1.2", 45678)),
            socket.timeout,
        ]

        # ループが無限にならないよう _running をフラグ管理
        original_recvfrom = mock_sock.recvfrom.side_effect
        call_count = [0]

        def controlled_recvfrom(_size):
            call_count[0] += 1
            if call_count[0] == 1:
                return valid_payload, ("192.168.1.2", 45678)
            net._running = False
            raise socket.timeout

        mock_sock.recvfrom.side_effect = controlled_recvfrom

        net._listen()

        self.assertEqual(net._votes[3], 1)

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
