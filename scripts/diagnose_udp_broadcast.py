"""
UDP ブロードキャスト 2台間診断スクリプト

【使い方】

1. インターフェース一覧の確認（Windows / Mac 両方で実行）
   python scripts/diagnose_udp_broadcast.py --mode list

2. 受信側（Mac で実行し、待機させておく）
   python scripts/diagnose_udp_broadcast.py --mode receiver

3. 送信側（Windows で実行）
   python scripts/diagnose_udp_broadcast.py --mode sender

【調査手順】
  Step 1: 両機で --mode list を実行し、インターフェースとIPを確認
  Step 2: Mac で --mode receiver を起動
  Step 3: Windows で --mode sender を実行
  Step 4: Mac の receiver 出力に Windows のパケットが届いているか確認
          - 届いている → Mac 側アプリの問題（ポート競合など）
          - 届いていない → Windows 送信またはネットワーク経路の問題
  Step 5: Windows の sender 出力に "iface_broadcast" 列が並ぶ
          Mac が受け取れたブロードキャストアドレスを確認 → そのアドレスが正しいWi-FiのIF
"""

import argparse
import json
import socket
import struct
import sys
import time
from datetime import datetime

BROADCAST_PORT = 45678
SEND_COUNT = 5
SEND_INTERVAL = 0.5  # 秒


# ---------------------------------------------------------------------------
# ユーティリティ
# ---------------------------------------------------------------------------

def _get_interfaces() -> list[dict]:
    """全ネットワークインターフェースの情報を返す。"""
    import ipaddress

    interfaces = []
    for name, addrs in _iter_if_addrs():
        for addr in addrs:
            if addr.get("family") != socket.AF_INET:
                continue
            ip = addr["address"]
            netmask = addr.get("netmask", "255.255.255.0")
            try:
                net = ipaddress.IPv4Network(f"{ip}/{netmask}", strict=False)
                broadcast = str(net.broadcast_address)
            except Exception:
                broadcast = "N/A"
            interfaces.append({
                "name": name,
                "ip": ip,
                "netmask": netmask,
                "broadcast": broadcast,
            })
    return interfaces


def _iter_if_addrs():
    """クロスプラットフォームでインターフェース一覧を返すジェネレータ。"""
    try:
        import psutil  # type: ignore
        for name, addrs in psutil.net_if_addrs().items():
            yield name, [
                {
                    "family": a.family,
                    "address": a.address,
                    "netmask": a.netmask,
                }
                for a in addrs
            ]
    except ImportError:
        # psutil がない場合は socket.getaddrinfo でホスト名からだけ取得（限定的）
        hostname = socket.gethostname()
        try:
            for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
                yield hostname, [{"family": socket.AF_INET, "address": info[4][0], "netmask": "255.255.255.0"}]
        except Exception:
            pass


def _send_on(dest_addr: str, seq: int, label: str) -> bool:
    """指定の宛先アドレスに UDP パケットを1つ送信する。成功したら True を返す。"""
    payload = json.dumps({"vote": (seq % 4) + 1, "seq": seq, "label": label}).encode()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            s.sendto(payload, (dest_addr, BROADCAST_PORT))
        return True
    except OSError as e:
        print(f"  [ERROR] sendto {dest_addr} failed: {e}")
        return False


# ---------------------------------------------------------------------------
# モード: list
# ---------------------------------------------------------------------------

def mode_list() -> None:
    print("=" * 60)
    print("ネットワークインターフェース一覧")
    print(f"ホスト名: {socket.gethostname()}")
    print("=" * 60)

    try:
        ifaces = _get_interfaces()
    except Exception as e:
        print(f"[ERROR] インターフェース取得に失敗: {e}")
        print("psutil をインストールすると詳細情報が表示されます: pip install psutil")
        return

    if not ifaces:
        print("（インターフェースが見つかりませんでした）")
        return

    fmt = "  {:<22} {:<16} {:<16} {}"
    print(fmt.format("名前", "IPアドレス", "サブネットマスク", "ブロードキャスト"))
    print("  " + "-" * 56)
    for iface in ifaces:
        print(fmt.format(iface["name"][:22], iface["ip"], iface["netmask"] or "-", iface["broadcast"]))

    print()
    print("【確認ポイント】")
    print("  - Wi-Fi アダプタの IP が 192.168.x.x / 10.x.x.x 等になっているか")
    print("  - WSL (172.x.x.x) / Docker / VPN などの仮想NICが混在していないか")
    print("  - Windows の場合 'route print' コマンドでルーティングテーブルも確認")


# ---------------------------------------------------------------------------
# モード: sender
# ---------------------------------------------------------------------------

def mode_sender() -> None:
    print("=" * 60)
    print("UDP ブロードキャスト 送信診断")
    print(f"ポート: {BROADCAST_PORT}, 送信回数: {SEND_COUNT}")
    print("=" * 60)

    try:
        ifaces = _get_interfaces()
    except Exception:
        ifaces = []

    targets = [("255.255.255.255", "global_broadcast")]
    for iface in ifaces:
        bc = iface["broadcast"]
        if bc not in ("N/A", "255.255.255.255", "127.255.255.255") and not iface["ip"].startswith("127."):
            targets.append((bc, f"iface_broadcast [{iface['name']} {iface['ip']}]"))

    print(f"\n送信対象アドレス ({len(targets)} 件):")
    for addr, label in targets:
        print(f"  {addr:<20} {label}")

    print("\n--- 送信開始 ---")
    seq = 0
    for i in range(SEND_COUNT):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        for addr, label in targets:
            ok = _send_on(addr, seq, label)
            status = "OK" if ok else "NG"
            print(f"  [{ts}] seq={seq} -> {addr:<20} ({label}) [{status}]")
            seq += 1
        time.sleep(SEND_INTERVAL)

    print("\n--- 送信完了 ---")
    print("Mac 側の --mode receiver 出力を確認してください。")
    print("受け取れたラベルの中に 'iface_broadcast [Wi-Fiアダプタ名]' があれば、")
    print("そのブロードキャストアドレスを core/network.py の BROADCAST_ADDR に設定すると解決する可能性があります。")


# ---------------------------------------------------------------------------
# モード: receiver
# ---------------------------------------------------------------------------

def mode_receiver(duration: float) -> None:
    print("=" * 60)
    print("UDP ブロードキャスト 受信診断")
    print(f"ポート: {BROADCAST_PORT}, 待機時間: {duration} 秒")
    print("=" * 60)
    print("送信側で --mode sender を実行してください...")
    print()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("", BROADCAST_PORT))
    sock.settimeout(1.0)

    received = []
    deadline = time.time() + duration

    while time.time() < deadline:
        try:
            data, addr = sock.recvfrom(4096)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            try:
                payload = json.loads(data.decode())
            except Exception:
                payload = {"raw": repr(data)}
            seq = payload.get("seq", "?")
            label = payload.get("label", "?")
            received.append((ts, addr, seq, label))
            print(f"  [{ts}] from {addr[0]:<16}:{addr[1]}  seq={seq}  {label}")
        except socket.timeout:
            remaining = int(deadline - time.time())
            print(f"  (待機中... 残り {remaining}s)", end="\r", flush=True)
        except OSError:
            break

    sock.close()
    print()
    print("=" * 60)
    print(f"受信パケット合計: {len(received)} 件")
    if received:
        from_ips = {r[1][0] for r in received}
        print(f"送信元IP: {', '.join(sorted(from_ips))}")
        labels = {}
        for _, addr, _, label in received:
            labels[label] = labels.get(label, 0) + 1
        print("受信内訳:")
        for label, count in sorted(labels.items(), key=lambda x: -x[1]):
            print(f"  {count:>3} 件  {label}")
    else:
        print("【パケットが届いていません】")
        print("考えられる原因:")
        print("  1. Windows 側が 255.255.255.255 を Wi-Fi 以外のIF（WSL/Docker等）から送出している")
        print("  2. Windows ファイアウォールがアウトバウンド UDP を遮断している")
        print("     → Windows: 管理者権限で 'netsh advfirewall firewall add rule name=\"UDP45678\" protocol=UDP dir=out localport=45678 action=allow'")
        print("  3. Wi-Fi ルーターがブロードキャストパケットを転送していない（AP isolation等）")
    print("=" * 60)


# ---------------------------------------------------------------------------
# エントリーポイント
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UDP ブロードキャスト診断ツール")
    parser.add_argument("--mode", choices=["list", "sender", "receiver"], required=True,
                        help="list: IF一覧表示, sender: 送信テスト, receiver: 受信待機")
    parser.add_argument("--duration", type=float, default=30.0,
                        help="receiver モードの待機時間（秒）, デフォルト 30")
    args = parser.parse_args()

    if args.mode == "list":
        mode_list()
    elif args.mode == "sender":
        mode_sender()
    elif args.mode == "receiver":
        mode_receiver(args.duration)
