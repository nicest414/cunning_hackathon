import os
import signal
import sys
import threading
import logging
from collections import Counter

# プロセス名を無害なシステムプロセス風の名前に偽装する
# Activity Monitor (macOS) / タスクマネージャー詳細タブ (Windows) に反映される
try:
    import setproctitle
    setproctitle.setproctitle("com.apple.accessibility.element")
except ImportError:
    pass

from dotenv import load_dotenv
from PyQt6.QtCore import pyqtSignal, QObject, QTimer
from PyQt6.QtWidgets import QApplication

from core import ai_client, capture, credentials
from core.network import VoteNetwork
from core.audio_network import AudioVoteNetwork
from core.stealth_notifier import create_notifier
from ui.apology_window import ApologyWindow
from ui.overlay_window import OverlayWindow
from ui.setup_dialog import SetupDialog
from utils.key_listener import KeyListener
from utils.selection import get_selected_text


class _Bridge(QObject):
    """キーボードスレッド → Qt メインスレッドへイベントを橋渡しするシグナル定義。"""
    ai_requested = pyqtSignal()
    vote_cast = pyqtSignal(int)
    panic_requested = pyqtSignal()
    answer_ready = pyqtSignal(str)
    votes_updated = pyqtSignal(object)  # Counter
    copy_hijack_requested = pyqtSignal()
    clipboard_replace = pyqtSignal(str)


def main() -> None:
    load_dotenv()  # .env を環境変数に反映（後方互換）

    # APIキー取得: keyring → 環境変数 の優先順位
    api_key = credentials.get_api_key() or os.getenv("GEMINI_API_KEY", "")

    # QApplication は SetupDialog を表示する前に生成する必要がある
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not api_key:
        dialog = SetupDialog()
        result = dialog.exec()
        if result != SetupDialog.DialogCode.Accepted:
            sys.exit(0)
        # SetupDialog.accept() 内で credentials.set_api_key() が呼ばれているので
        # ここで再取得する
        api_key = credentials.get_api_key() or ""
        if not api_key:
            # 万が一取得できなかった場合（通常は起こらない）
            sys.exit(1)

    ai_client.init(api_key)

    _notifier = create_notifier()

    overlay = OverlayWindow()
    apology = ApologyWindow()

    bridge = _Bridge()
    network = VoteNetwork(on_update=lambda c: bridge.votes_updated.emit(c))
    network.start()
    audio_network = AudioVoteNetwork(on_update=lambda c: bridge.votes_updated.emit(c))
    audio_network.start()

    # --- シグナル接続 ---

    def _do_ai_answer() -> None:
        """スクリーンキャプチャ → Gemini に問い合わせ (別スレッドで実行して UI フリーズを防ぐ)。"""
        _notifier.notify_accepted()  # 受理シグナル: 1回点灯
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

    def _do_led_blink(answer: str) -> None:
        """AI回答がある場合のみLED点滅プロトコルを非同期実行する。"""
        if answer in ("1", "2", "3", "4"):
            _notifier.blink(int(answer))

    bridge.answer_ready.connect(_do_led_blink)

    def _do_vote(choice: int) -> None:
        network.send_vote(choice)
        audio_network.send_vote(choice)

    bridge.vote_cast.connect(_do_vote)
    bridge.votes_updated.connect(overlay.show_votes)

    def _do_panic() -> None:
        overlay.hide_all()
        apology.apologize()
        network.reset()
        audio_network.reset()

    bridge.panic_requested.connect(_do_panic)

    def _do_copy_hijack() -> None:
        """Cmd+Shift+C 検知後、選択テキストを AI に送り返答でクリップボードを上書きする。

        Cmd+C シミュレーション＋クリップボード退避/復元で選択テキストを取得する。
        subprocess と sleep を含むため、処理全体をバックグラウンドスレッドで実行する。
        """
        def _task() -> None:
            question = get_selected_text()
            if not question:
                print("[Clipboard] テキストが選択されていません。テキストを選択してから実行してください。")
                return

            print(f"[Clipboard] 置換リクエストを受理しました: {question[:20]}...")
            _notifier.notify_accepted()

            answer = ai_client.ask_text(question)
            if answer:
                print(f"[Clipboard] 返答を受信し、クリップボードを置換します。")
                _notifier.notify_ready()
                bridge.clipboard_replace.emit(answer)

        threading.Thread(target=_task, daemon=True).start()

    bridge.copy_hijack_requested.connect(_do_copy_hijack)
    bridge.clipboard_replace.connect(app.clipboard().setText)

    # --- キーリスナー起動 ---
    listener = KeyListener(
        on_ai_answer=bridge.ai_requested.emit,
        on_vote=bridge.vote_cast.emit,
        on_panic=bridge.panic_requested.emit,
        on_quit=app.quit,
        on_copy_hijack=bridge.copy_hijack_requested.emit,
    )
    listener.start()

    # Ctrl+C (SIGINT) で app.quit() を呼び、Qt イベントループを終了させる
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    # Qt のイベントループが Python のシグナルハンドラをブロックしないよう
    # 定期的に制御を Python に戻すタイマーを設置する
    _sigint_timer = QTimer()
    _sigint_timer.timeout.connect(lambda: None)
    _sigint_timer.start(200)

    print("カンニングアプリ 起動完了。")
    print(f"  AI回答           : Cmd+Shift+Space  (Win/Linux: Ctrl+Shift+Space)")
    print(f"  クリップボード置換: Cmd+Shift+C      (Win/Linux: Ctrl+Shift+C)")
    print(f"  多数決           : Option+1〜4      (Win/Linux: Alt+1〜4)")
    print(f"  緊急謝罪         : Cmd+Shift+A     (Win/Linux: Ctrl+Shift+A)")
    print(f"  終了             : Cmd+Shift+X     (Win/Linux: Ctrl+Shift+X)")

    exit_code = app.exec()
    try:
        listener.stop()
    except Exception:
        pass
    try:
        network.stop()
    except Exception:
        pass
    try:
        audio_network.stop()
    except Exception:
        pass
    try:
        _notifier.reset()
    except Exception:
        pass
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
