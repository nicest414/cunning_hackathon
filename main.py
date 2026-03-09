"""shadow_answer — 全自動カンニング風ネタアプリ エントリーポイント。"""
import os
import signal
import sys
from collections import Counter

from dotenv import load_dotenv
from PyQt6.QtCore import pyqtSignal, QObject, QTimer
from PyQt6.QtWidgets import QApplication

from core import ai_client, capture
from core.network import VoteNetwork
from ui.apology_window import ApologyWindow
from ui.overlay_window import OverlayWindow
from utils.key_listener import KeyListener


class _Bridge(QObject):
    """キーボードスレッド → Qt メインスレッドへイベントを橋渡しするシグナル定義。"""
    ai_requested = pyqtSignal()
    vote_cast = pyqtSignal(int)
    panic_requested = pyqtSignal()
    answer_ready = pyqtSignal(str)
    votes_updated = pyqtSignal(object)  # Counter


def main() -> None:
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY が設定されていません。.env を確認してください。")
        sys.exit(1)

    ai_client.init(api_key)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    overlay = OverlayWindow()
    apology = ApologyWindow()

    bridge = _Bridge()
    network = VoteNetwork(on_update=lambda c: bridge.votes_updated.emit(c))
    network.start()

    # --- シグナル接続 ---

    def _do_ai_answer() -> None:
        """スクリーンキャプチャ → Gemini に問い合わせ (別スレッドで実行して UI フリーズを防ぐ)。"""
        def _task():
            try:
                img = capture.capture_screen()
                answer = ai_client.ask(img)
                bridge.answer_ready.emit(answer)
            except Exception as e:
                bridge.answer_ready.emit("?")
                print(f"[AI ERROR] {e}")

        import threading
        t = threading.Thread(target=_task, daemon=True)
        t.start()

    bridge.ai_requested.connect(_do_ai_answer)
    bridge.answer_ready.connect(overlay.show_answer)

    def _do_vote(choice: int) -> None:
        network.send_vote(choice)

    bridge.vote_cast.connect(_do_vote)
    bridge.votes_updated.connect(overlay.show_votes)

    def _do_panic() -> None:
        overlay.hide_all()
        apology.apologize()
        network.reset()

    bridge.panic_requested.connect(_do_panic)

    # --- キーリスナー起動 ---
    listener = KeyListener(
        on_ai_answer=bridge.ai_requested.emit,
        on_vote=bridge.vote_cast.emit,
        on_panic=bridge.panic_requested.emit,
    )
    listener.start()

    # Ctrl+C (SIGINT) で app.quit() を呼び、Qt イベントループを終了させる
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Qt のイベントループが Python のシグナルハンドラをブロックしないよう
    # 定期的に制御を Python に戻すタイマーを設置する
    _sigint_timer = QTimer()
    _sigint_timer.timeout.connect(lambda: None)
    _sigint_timer.start(200)

    print("shadow_answer 起動完了。")
    print(f"  AI回答   : Cmd+Shift+Space  (Win/Linux: Ctrl+Shift+Space)")
    print(f"  多数決   : Option+1〜4      (Win/Linux: Alt+1〜4)")
    print(f"  緊急謝罪 : Cmd+Shift+Q     (Win/Linux: Ctrl+Shift+Q)")
    print("終了するには Ctrl+C を押してください。")

    exit_code = app.exec()
    try:
        listener.stop()
    except Exception:
        pass
    try:
        network.stop()
    except Exception:
        pass
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
