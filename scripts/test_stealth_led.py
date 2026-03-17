"""ステルスLED通知の単体動作確認スクリプト。

このスクリプトを実行すると、Caps LockのLEDが点滅プロトコル（3回点滅）を実行します。
"""
import sys
import time
import os

# プロジェクトルートをパスに追加して core モジュールをインポート可能にする
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.stealth_notifier import create_notifier

def main():
    print("=== ステルスLED通知 単体テスト ===")
    
    # Notifierの初期化（Windowsの場合はUACが必要な場合があります）
    notifier = create_notifier()
    
    # フォールバック（_NullNotifier）になった場合は終了
    if type(notifier).__name__ == "_NullNotifier":
        print("[!] LED通知が有効な環境ではないか、権限が不足しています。")
        print("    Windowsの場合は「管理者として実行」を試してください。")
        return

    print("-------------------------------------------------")
    print("これから点滅プロトコルをテストします。")
    print("キーボードの Caps Lock ランプに注目してください。")
    print("-------------------------------------------------")
    print("【期待される動作】")
    print(" 1. 開始合図: チカチカッ (2回)")
    print(" 2. 待機    : 1秒消灯")
    print(" 3. 答え    : ゆっくり 3 回点灯")
    print(" 4. 待機    : 1秒消灯")
    print(" 5. 終了合図: チカッ (1回)")
    print("-------------------------------------------------\n")

    input("準備ができたら Enter を押して開始...")

    print("=> blink(3) 実行中...")
    notifier.blink(3)
    
    # 非同期で実行されるため、メインスレッドを待機させる
    # 点滅が終わるまで余裕をもって 6 秒待つ
    time.sleep(6)
    
    print("=> テスト完了。論理的な Caps Lock が切り替わっていないことを確認してください。")

if __name__ == "__main__":
    main()
