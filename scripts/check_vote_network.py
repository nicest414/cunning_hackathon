"""
P2P 多数決ネットワーク 1台動作確認スクリプト

「受信側」をサブプロセスで起動し、メインプロセスから UDP ブロードキャストを
送信して、実際の通信が成立するか確認する。

使い方:
    python scripts/check_vote_network.py

仕組み:
    - メインプロセス: 生 UDP ソケットで投票を送信（バインドなし）
    - サブプロセス  : VoteNetwork でポートをバインドして受信し、
                     受け取った Counter を JSON で stdout に出力
"""
import json
import socket
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT_ROOT = str(Path(__file__).parent.parent)
BROADCAST_PORT = 45678
BROADCAST_ADDR = "255.255.255.255"
PASS = "✓ PASS"
FAIL = "✗ FAIL"


# ---------------------------------------------------------------------------
# サブプロセス用: --mode receiver で起動したときのエントリー
# ---------------------------------------------------------------------------
def _receiver_main(duration: float) -> None:
    """VoteNetwork を起動し、受け取った Counter を JSON で stdout に出力する。"""
    sys.path.insert(0, PROJECT_ROOT)
    from core.network import VoteNetwork

    def on_update(counter: Counter) -> None:
        # Counter をシリアライズして flush することでメインプロセスが読める
        print(json.dumps(dict(counter)), flush=True)

    net = VoteNetwork(on_update=on_update)
    net.start()
    time.sleep(duration)
    net.stop()


# ---------------------------------------------------------------------------
# 送信ヘルパー: バインド不要の生ソケットで UDP ブロードキャスト送信
# ---------------------------------------------------------------------------
def _send_vote(choice: int) -> None:
    payload = json.dumps({"vote": choice}).encode()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(payload, (BROADCAST_ADDR, BROADCAST_PORT))


# ---------------------------------------------------------------------------
# テスト実行
# ---------------------------------------------------------------------------
def _start_receiver(duration: float) -> subprocess.Popen:
    """受信側サブプロセスを起動する。"""
    return subprocess.Popen(
        [sys.executable, __file__, "--mode", "receiver",
         "--duration", str(duration)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _read_counters(proc: subprocess.Popen) -> list[Counter]:
    """サブプロセスの stdout を読んで Counter のリストを返す。"""
    stdout, _ = proc.communicate()
    counters = []
    for line in stdout.strip().splitlines():
        try:
            counters.append(Counter({int(k): v for k, v in json.loads(line).items()}))
        except (json.JSONDecodeError, ValueError):
            pass
    return counters


def run_checks() -> bool:
    all_passed = True

    print("=" * 52)
    print("VoteNetwork 動作確認 (1台テスト)")
    print("=" * 52)

    # --------------------------------------------------
    # テスト 1: vote=2 を送信 → 受信側でカウントされるか
    # --------------------------------------------------
    print("\n[1] vote=2 を1回送信 → 受信側でカウント確認")

    proc = _start_receiver(duration=1.5)
    time.sleep(0.4)   # サブプロセスのソケット準備待ち

    _send_vote(2)
    time.sleep(0.3)   # 受信待ち

    proc.terminate()
    counters = _read_counters(proc)
    received = any(c.get(2, 0) >= 1 for c in counters)
    status = PASS if received else FAIL
    print(f"    結果: {status}  (受け取った更新: {[dict(c) for c in counters]})")
    if not received:
        all_passed = False

    # --------------------------------------------------
    # テスト 2: 複数票の累積
    # --------------------------------------------------
    print("\n[2] vote=1 を2回、vote=3 を1回送信 → 累積集計確認")

    proc = _start_receiver(duration=2.0)
    time.sleep(0.4)

    _send_vote(1)
    _send_vote(1)
    _send_vote(3)
    time.sleep(0.5)

    proc.terminate()
    counters = _read_counters(proc)
    if counters:
        last = counters[-1]
        ok = last.get(1, 0) >= 2 and last.get(3, 0) >= 1
    else:
        ok = False

    status = PASS if ok else FAIL
    last_str = dict(counters[-1]) if counters else "(なし)"
    print(f"    結果: {status}  (最終集計: {last_str})")
    if not ok:
        all_passed = False

    # --------------------------------------------------
    # テスト 3: 連続4票が順番通り受信されるか
    # --------------------------------------------------
    print("\n[3] vote=1,2,3,4 を順に送信 → 4種すべて受信確認")

    proc = _start_receiver(duration=2.0)
    time.sleep(0.4)

    for choice in (1, 2, 3, 4):
        _send_vote(choice)
        time.sleep(0.05)
    time.sleep(0.5)

    proc.terminate()
    counters = _read_counters(proc)
    if counters:
        last = counters[-1]
        ok = all(last.get(i, 0) >= 1 for i in (1, 2, 3, 4))
    else:
        ok = False

    status = PASS if ok else FAIL
    last_str = dict(counters[-1]) if counters else "(なし)"
    print(f"    結果: {status}  (最終集計: {last_str})")
    if not ok:
        all_passed = False

    # --------------------------------------------------
    # 最終結果
    # --------------------------------------------------
    print("\n" + "=" * 52)
    if all_passed:
        print("全テスト通過 — UDP ブロードキャスト通信は正常です。")
        print("2台間での多数決機能は動作する見込みです。")
    else:
        print("失敗したテストがあります。")
        print("")
        print("確認事項:")
        print("  - macOS : システム設定 > ファイアウォール で Python を許可")
        print("  - Windows: ファイアウォールで UDP 45678 番ポートを開放")
        print("  - OS が UDP ブロードキャストの自己受信を制限している場合は")
        print("    2台テストで再確認してください。")
    print("=" * 52)

    return all_passed


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if "--mode" in sys.argv and sys.argv[sys.argv.index("--mode") + 1] == "receiver":
        duration_idx = sys.argv.index("--duration") + 1 if "--duration" in sys.argv else None
        duration = float(sys.argv[duration_idx]) if duration_idx else 3.0
        _receiver_main(duration)
    else:
        ok = run_checks()
        sys.exit(0 if ok else 1)
