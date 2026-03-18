"""グローバルホットキー登録・管理モジュール (pynput ベース)。"""
import logging
import os
import platform
import threading
from typing import Callable

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

# ビルド版 (console=False) でもエラーを確認できるようファイルにログを出力する
# KL_DEBUG=1 環境変数を設定するとキー入力を含む DEBUG ログが有効になる
_KL_DEBUG = os.environ.get("KL_DEBUG") == "1"

def _setup_file_logger() -> logging.Logger:
    logger = logging.getLogger("KeyListener")
    if logger.handlers:
        return logger
    try:
        _sys = platform.system()
        if _sys == "Darwin":
            log_dir = os.path.join(os.path.expanduser("~"), "Library", "Logs", "InputMonitor")
        elif _sys == "Windows":
            log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "InputMonitor", "Logs")
        else:
            log_dir = os.path.join(os.path.expanduser("~"), ".local", "share", "InputMonitor", "logs")
        os.makedirs(log_dir, exist_ok=True)
        handler = logging.FileHandler(os.path.join(log_dir, "key_listener.log"), encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        logger.addHandler(handler)
    except Exception:
        # ファイルログが作れなくても NullHandler でフォールバックして起動を継続する
        logger.addHandler(logging.NullHandler())
    logger.setLevel(logging.DEBUG if _KL_DEBUG else logging.INFO)
    return logger

_log = _setup_file_logger()

_IS_MAC = platform.system() == "Darwin"


def _ax_is_process_trusted() -> bool:
    """macOS: AXIsProcessTrusted() の結果を返す。非 macOS では常に True。"""
    if not _IS_MAC:
        return True
    try:
        import ctypes, ctypes.util
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices") or "")
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return False

# macOS: command / Windows・Linux: ctrl
_MOD_KEY = Key.cmd if _IS_MAC else Key.ctrl


def _print_mac_warning() -> None:
    if _IS_MAC:
        print(
            "\n[注意] macOS ユーザーへ:\n"
            "  キーボード監視には「アクセシビリティ」権限が必要です。\n"
            "  システム設定 > プライバシーとセキュリティ > アクセシビリティ\n"
            "  に、このターミナル（または IDE）を追加してください。\n"
        )


class KeyListener:
    def __init__(
        self,
        on_ai_answer: Callable[[], None],
        on_vote: Callable[[int], None],
        on_panic: Callable[[], None],
        on_quit: Callable[[], None] = lambda: None,
        on_copy_hijack: Callable[[], None] = lambda: None,
    ) -> None:
        self._on_ai_answer = on_ai_answer
        self._on_vote = on_vote
        self._on_panic = on_panic
        self._on_quit = on_quit
        self._on_copy_hijack = on_copy_hijack

        self._pressed: set = set()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        """pynput リスナーをバックグラウンドスレッドで起動する。ウォッチドッグも起動。"""
        _print_mac_warning()
        import sys
        try:
            import pynput
            pynput_ver = pynput.__version__
        except Exception:
            pynput_ver = "unknown"
        ax_trusted = _ax_is_process_trusted()
        _log.info(
            "[KeyListener] start() 呼び出し platform=%s python=%s pynput=%s AXIsProcessTrusted=%s",
            platform.system(), sys.version.split()[0], pynput_ver, ax_trusted,
        )
        self._stopped = False
        self._start_listener()
        self._watchdog_thread = threading.Thread(target=self._watchdog, daemon=True)
        self._watchdog_thread.start()

    def _start_listener(self) -> None:
        """リスナーを（再）起動する。"""
        try:
            if self._listener:
                try:
                    self._listener.stop()
                except Exception:
                    pass
            self._pressed.clear()
            self._listener = keyboard.Listener(
                on_press=self._on_press,
                on_release=self._on_release,
                suppress=False,
            )
            self._listener.start()
            msg = "[KeyListener] リスナーを起動しました。"
            print(msg)
            _log.info(msg)
            # 起動後の内部例外チェックはウォッチドッグの初回ティックで行う（メインスレッドをブロックしない）
        except Exception as e:
            msg = f"[KeyListener] リスナー起動失敗: {e}"
            print(msg)
            _log.exception(msg)

    def _watchdog(self) -> None:
        """リスナーが死んでいたら自動で再起動するウォッチドッグ。"""
        import time
        _health_tick = 0
        while not self._stopped:
            time.sleep(1.0)
            if self._stopped:
                break
            _health_tick += 1

            # 起動直後チェック（1秒後）: pynput 内部例外を確認する
            if _health_tick == 1:
                exc = getattr(self._listener, "_exc", None) if self._listener else None
                alive = self._listener.is_alive() if self._listener else False
                _log.info("[KeyListener] 起動後チェック: is_alive=%s _exc=%s", alive, exc)
                if exc:
                    _log.error("[KeyListener] pynput 内部例外を検出: %s", exc,
                               exc_info=(type(exc), exc, exc.__traceback__))

            # 10秒ごとに定期ヘルスレポートを出力する
            if _health_tick % 10 == 0:
                alive = self._listener.is_alive() if self._listener else False
                exc = getattr(self._listener, "_exc", None) if self._listener else None
                ax = _ax_is_process_trusted()
                _log.info(
                    "[KeyListener] ヘルスチェック: is_alive=%s _exc=%s AXIsProcessTrusted=%s",
                    alive, exc, ax,
                )

            if self._listener is None or not self._listener.is_alive():
                exc = getattr(self._listener, "_exc", None) if self._listener else None
                msg = f"[KeyListener] リスナーが停止を検知 → 再起動します。(停止前の_exc={exc})"
                print(msg)
                _log.warning(msg)
                self._start_listener()

    def stop(self) -> None:
        self._stopped = True
        if self._listener:
            self._listener.stop()
            self._listener = None

    # --- 内部処理 ---

    def _on_press(self, key) -> None:
        try:
            if _KL_DEBUG:
                _log.debug("[KeyListener] KEY_PRESS: %s", key)
            self._pressed.add(key)
            self._check_hotkeys()
        except Exception as e:
            msg = f"[KeyListener] on_press エラー: {e}"
            print(msg)
            _log.exception(msg)

    def _on_release(self, key) -> None:
        try:
            if _KL_DEBUG:
                _log.debug("[KeyListener] KEY_RELEASE: %s", key)
            self._pressed.discard(key)
        except Exception as e:
            msg = f"[KeyListener] on_release エラー: {e}"
            print(msg)
            _log.exception(msg)

    # macOS ANSI 仮想キーコード（Option 修飾時も変わらない）
    _MAC_NUM_VK = {1: 18, 2: 19, 3: 20, 4: 21}
    # macOS ANSI 仮想キーコード（アルファベット）
    _MAC_ALPHA_VK = {
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7,
        "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14, "r": 15,
        "y": 16, "t": 17, "u": 32, "i": 34, "o": 31, "p": 35, "l": 37,
        "j": 38, "k": 40, "n": 45, "m": 46,
    }

    def _has_alpha(self, char: str) -> bool:
        """アルファベットキー char が押されているか（macOS の Cmd 修飾による char=None を回避）"""
        char = char.lower()
        for k in self._pressed:
            if _IS_MAC and hasattr(k, "vk") and k.vk == self._MAC_ALPHA_VK.get(char):
                return True
            if not _IS_MAC and hasattr(k, "vk") and k.vk == ord(char.upper()):
                return True
            if hasattr(k, "char") and k.char and k.char.lower() == char:
                return True
        return False

    def _has_num(self, n: int) -> bool:
        """数字キー n が押されているか（macOS の Option 修飾による文字変換を回避）"""
        for k in self._pressed:
            # vk ベースで判定（修飾キーによる char 変換を無視できる）
            if _IS_MAC and hasattr(k, "vk") and k.vk == self._MAC_NUM_VK.get(n):
                return True
            # Windows/Linux: vk で判定
            if not _IS_MAC and hasattr(k, "vk") and k.vk == ord(str(n)):
                return True
            # Windows/Linux: char で判定
            if hasattr(k, "char") and k.char == str(n):
                return True
        return False

    def _has(self, *keys) -> bool:
        """押下中のキーセットが指定キーをすべて含むか確認する。左右の修飾キーも考慮する。"""
        # 現在押されているキーの名前（文字列）の集合を取得
        # Key.ctrl_l なら "ctrl_l", KeyCode.from_char("a") なら "a" のようになる
        pressed_names = set()
        for k in self._pressed:
            if hasattr(k, "name") and k.name:
                pressed_names.add(k.name)
            elif hasattr(k, "char") and k.char:
                pressed_names.add(str(k.char).lower())
            
        for k in keys:
            # 必要なキーの名前を取得
            name = None
            if hasattr(k, "name") and k.name:
                name = k.name
            elif hasattr(k, "char") and k.char:
                name = str(k.char).lower()
                
            if not name:
                continue

            # 修飾キーの抽象化（ctrl_l / ctrl_r のどちらかが押されていれば ctrl 押下とみなす、など）
            if name in ("ctrl", "cmd", "shift", "alt"):
                if f"{name}_l" in pressed_names or f"{name}_r" in pressed_names:
                    continue  # LかRが押されているのでOK
                if name in pressed_names:
                    continue
                return False
                
            # 一般キーの判定
            if name not in pressed_names:
                return False

        return True

    def _safe_call(self, func: Callable) -> None:
        """コールバック内で例外が起きても pynput リスナーを死なせないためのラッパー"""
        try:
            func()
        except Exception as e:
            print(f"[Key ERROR] {e}")

    def _check_hotkeys(self) -> None:
        try:
            mod = _MOD_KEY
            shift = Key.shift
            alt = Key.alt  # macOS では option キーが alt として認識される

            # Cmd/Ctrl + Shift + Space → AI回答
            if self._has(mod, shift, Key.space):
                self._pressed.clear()  # **全体をクリアして状態不整合を防ぐ**
                threading.Thread(target=self._safe_call, args=(self._on_ai_answer,), daemon=True).start()
                return

            # Cmd/Ctrl + Shift + A → パニック
            if self._has(mod, shift) and self._has_alpha("a"):
                self._pressed.clear()
                threading.Thread(target=self._safe_call, args=(self._on_panic,), daemon=True).start()
                return

            # Cmd/Ctrl + Shift + X → アプリ終了
            if self._has(mod, shift) and self._has_alpha("x"):
                self._pressed.clear()
                threading.Thread(target=self._safe_call, args=(self._on_quit,), daemon=True).start()
                return

            # Cmd/Ctrl + Shift + C → クリップボードAI置換
            # Cmd+C（コピー）と分離することで OS との競合を完全に回避する。
            # 選択中のテキストを内部で Cmd/Ctrl+C シミュレーションにより取得する。
            if self._has(mod, shift) and self._has_alpha("c"):
                self._pressed.clear()
                threading.Thread(target=self._safe_call, args=(self._on_copy_hijack,), daemon=True).start()
                return

            # Alt/Option + 1〜4 → 多数決
            for i in range(1, 5):
                if self._has(alt) and self._has_num(i):
                    self._pressed.clear()
                    choice = i
                    threading.Thread(
                        target=self._safe_call, args=(lambda n=choice: self._on_vote(n),), daemon=True
                    ).start()
                    return
        except Exception as e:
            print(f"[Key Hook Error] {e}")
