"""UDP ブロードキャストによるサーバーレス P2P 多数決モジュール。"""
import json
import socket
import threading
from collections import Counter
from typing import Callable

BROADCAST_PORT = 45678
BROADCAST_ADDR = "255.255.255.255"
_BUFFER_SIZE = 1024


class VoteNetwork:
    def __init__(self, on_update: Callable[[Counter], None]) -> None:
        """
        on_update: 集計結果 Counter({1: 2, 3: 1, ...}) を受け取るコールバック。
        """
        self._on_update = on_update
        self._votes: Counter = Counter()
        self._lock = threading.Lock()

        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP通信
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind(("", BROADCAST_PORT))
        self._sock.settimeout(1.0)

        self._running = False
        self._thread = threading.Thread(target=self._listen, daemon=True)

    def start(self) -> None:
        self._running = True
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._sock.close()

    def send_vote(self, choice: int) -> None:
        """自分の回答 (1〜4) をブロードキャスト送信する。"""
        payload = json.dumps({"vote": choice}).encode()
        self._sock.sendto(payload, (BROADCAST_ADDR, BROADCAST_PORT))
        # 自分の票も集計に加える
        with self._lock:
            self._votes[choice] += 1
        self._on_update(Counter(self._votes))

    def reset(self) -> None:
        with self._lock:
            self._votes.clear()
        self._on_update(Counter())

    def _listen(self) -> None:
        while self._running:
            try:
                data, _ = self._sock.recvfrom(_BUFFER_SIZE)
                payload = json.loads(data.decode())
                choice = int(payload.get("vote", 0))
                if choice in (1, 2, 3, 4):
                    with self._lock:
                        self._votes[choice] += 1
                    self._on_update(Counter(self._votes))
            except (socket.timeout, OSError):
                pass
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
