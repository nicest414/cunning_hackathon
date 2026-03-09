"""グローバルホットキー登録・管理モジュール (pynput ベース)。"""
import platform
import threading
from typing import Callable

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

_IS_MAC = platform.system() == "Darwin"

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
    ) -> None:
        self._on_ai_answer = on_ai_answer
        self._on_vote = on_vote
        self._on_panic = on_panic
        self._on_quit = on_quit

        self._pressed: set = set()
        self._listener: keyboard.Listener | None = None

    def start(self) -> None:
        """pynput リスナーをバックグラウンドスレッドで起動する。"""
        _print_mac_warning()
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None

    # --- 内部処理 ---

    def _on_press(self, key) -> None:
        self._pressed.add(key)
        self._check_hotkeys()

    def _on_release(self, key) -> None:
        self._pressed.discard(key)

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

            # Cmd/Ctrl + Shift + Q → パニック
            if self._has(mod, shift, KeyCode.from_char("q")):
                self._pressed.clear()
                threading.Thread(target=self._safe_call, args=(self._on_panic,), daemon=True).start()
                return

            # Cmd/Ctrl + C → アプリ終了 (KeyboardInterrupt の代わり)
            if self._has(mod, KeyCode.from_char("c")):
                self._pressed.clear()
                threading.Thread(target=self._safe_call, args=(self._on_quit,), daemon=True).start()
                return

            # Alt/Option + 1〜4 → 多数決
            for i in range(1, 5):
                if self._has(alt, KeyCode.from_char(str(i))):
                    self._pressed.clear()
                    choice = i
                    threading.Thread(
                        target=self._safe_call, args=(lambda n=choice: self._on_vote(n),), daemon=True
                    ).start()
                    return
        except Exception as e:
            print(f"[Key Hook Error] {e}")
