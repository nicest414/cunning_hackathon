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


def _get_local_ip() -> str:
    """デフォルトインターフェースのローカル IP アドレスを返す。取得できない場合は '127.0.0.1'。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _get_broadcast_addr() -> str:
    """デフォルトインターフェースのブロードキャストアドレスを動的に取得する。

    UDP ソケットで外部アドレスに「接続」することでデフォルト経路の
    ローカル IP を取得し、/24 を仮定してブロードキャストアドレスを算出する。
    取得できない場合は 255.255.255.255（limited broadcast）へフォールバック。
    """
    try:
        local_ip = _get_local_ip()
        # 一般的な家庭/オフィス Wi-Fi は /24 のため最終オクテットを 255 に置換
        prefix = local_ip.rsplit(".", 1)[0]
        return f"{prefix}.255"
    except OSError:
        return "255.255.255.255"


BROADCAST_ADDR = _get_broadcast_addr()  # モジュールロード時に一度だけ解決


class VoteNetwork:
    def __init__(
        self,
        on_update: Callable[[Counter], None],
        on_question_changed: Callable[[int], None] | None = None,
    ) -> None:
        """
        on_update: 集計結果 Counter({1: 2, 3: 1, ...}) を受け取るコールバック。
        on_question_changed: 問題番号が変わったとき (question_id) を受け取るコールバック。
        """
        self._on_update = on_update
        self._on_question_changed = on_question_changed
        self._votes: Counter = Counter()
        self._current_question: int = 1
        self._lock = threading.Lock()
        self._local_ip: str = _get_local_ip()  # 自己送信パケット除外用

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
        """自分の回答 (1〜4) をブロードキャスト送信し、ローカルにも即時集計する。

        UDP ブロードキャストが自己受信できない環境でも確実に自票を反映するため、
        送信と同時にローカルの _votes に加算する。
        _listen() 側では同じ IP からのパケットを除外することで二重加算を防ぐ。
        """
        with self._lock:
            question_id = self._current_question
        payload = json.dumps({"type": "vote", "vote": choice, "question_id": question_id}).encode()
        self._sock.sendto(payload, (BROADCAST_ADDR, BROADCAST_PORT))
        if choice in (1, 2, 3, 4):
            with self._lock:
                self._votes[choice] += 1
                current_votes = Counter(self._votes)
            self._on_update(current_votes)

    def send_question(self, question_id: int) -> None:
        """問題番号をブロードキャストし、ローカルの投票をリセットする。"""
        with self._lock:
            self._current_question = question_id
            self._votes.clear()
        payload = json.dumps({"type": "question", "question_id": question_id}).encode()
        self._sock.sendto(payload, (BROADCAST_ADDR, BROADCAST_PORT))
        self._on_update(Counter())
        if self._on_question_changed:
            self._on_question_changed(question_id)

    def shift_question(self, delta: int) -> int:
        """問題番号を増減してブロードキャストし、新しい問題番号を返す。"""
        with self._lock:
            self._current_question = max(1, self._current_question + delta)
            new_question = self._current_question
            self._votes.clear()
        payload = json.dumps({"type": "question", "question_id": new_question}).encode()
        self._sock.sendto(payload, (BROADCAST_ADDR, BROADCAST_PORT))
        self._on_update(Counter())
        if self._on_question_changed:
            self._on_question_changed(new_question)
        return new_question

    def get_current_question(self) -> int:
        with self._lock:
            return self._current_question

    def reset(self) -> None:
        with self._lock:
            self._votes.clear()
        self._on_update(Counter())

    def _listen(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(_BUFFER_SIZE)
                if addr[0] == self._local_ip:
                    continue  # 自己送信パケットは send_vote() 側で集計済みのため無視
                if os.environ.get("VOTE_DEBUG"):
                    print(f"[VoteNetwork] recv from {addr}: {data!r}", file=sys.stderr, flush=True)
                payload = json.loads(data.decode())
                msg_type = payload.get("type", "vote")

                if msg_type == "question":
                    question_id = int(payload.get("question_id", 1))
                    with self._lock:
                        self._current_question = question_id
                        self._votes.clear()
                    self._on_update(Counter())
                    if self._on_question_changed:
                        self._on_question_changed(question_id)
                else:  # "vote" またはフィールドなし（旧フォーマット互換）
                    choice = int(payload.get("vote", 0))
                    if choice not in (1, 2, 3, 4):
                        continue
                    raw_qid = payload.get("question_id")
                    with self._lock:
                        if raw_qid is not None and int(raw_qid) != self._current_question:
                            continue  # 別の問題の票は無視
                        self._votes[choice] += 1
                        current_votes = Counter(self._votes)
                    self._on_update(current_votes)
            except (socket.timeout, OSError):
                pass
            except (json.JSONDecodeError, ValueError, KeyError):
                pass
