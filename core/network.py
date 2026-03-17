"""UDP ブロードキャストによるサーバーレス P2P 多数決モジュール。"""
import json
import os
import socket
import sys
import threading
from collections import Counter
from typing import Callable

BROADCAST_PORT = 45678
_BUFFER_SIZE = 1024


def _get_broadcast_addr() -> str:
    """デフォルトインターフェースのブロードキャストアドレスを動的に取得する。

    UDP ソケットで外部アドレスに「接続」することでデフォルト経路の
    ローカル IP を取得し、/24 を仮定してブロードキャストアドレスを算出する。
    取得できない場合は 255.255.255.255（limited broadcast）へフォールバック。
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            local_ip: str = s.getsockname()[0]
        # 一般的な家庭/オフィス Wi-Fi は /24 のため最終オクテットを 255 に置換
        prefix = local_ip.rsplit(".", 1)[0]
        return f"{prefix}.255"
    except OSError:
        return "255.255.255.255"


BROADCAST_ADDR = _get_broadcast_addr()  # モジュールロード時に一度だけ解決


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
        # macOS では SO_REUSEPORT が必要。macOS 以外では設定しない。
        if sys.platform == "darwin" and hasattr(socket, "SO_REUSEPORT"):
            self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
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
        """自分の回答 (1〜4) をブロードキャスト送信する。集計は受信側 (_listen) で行う。"""
        payload = json.dumps({"vote": choice}).encode()
        self._sock.sendto(payload, (BROADCAST_ADDR, BROADCAST_PORT))

    def reset(self) -> None:
        with self._lock:
            self._votes.clear()
        self._on_update(Counter())

    def _listen(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(_BUFFER_SIZE)
                if os.environ.get("VOTE_DEBUG"):
                    print(f"[VoteNetwork] recv from {addr}: {data!r}", file=sys.stderr, flush=True)
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
