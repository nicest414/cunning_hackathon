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
    ) -> None:
        self._on_ai_answer = on_ai_answer
        self._on_vote = on_vote
        self._on_panic = on_panic

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
        """押下中のキーセットが指定キーをすべて含むか確認する。"""
        for k in keys:
            if k not in self._pressed:
                return False
        return True

    def _check_hotkeys(self) -> None:
        mod = _MOD_KEY
        shift = Key.shift
        alt = Key.alt  # macOS では option キーが alt として認識される

        # Cmd/Ctrl + Shift + Space → AI回答
        if self._has(mod, shift, Key.space):
            self._pressed.clear()  # 連続発火防止
            threading.Thread(target=self._on_ai_answer, daemon=True).start()
            return

        # Cmd/Ctrl + Shift + A → パニック
        if self._has(mod, shift, KeyCode.from_char("a")):
            self._pressed.clear()
            threading.Thread(target=self._on_panic, daemon=True).start()
            return

        # Alt/Option + 1〜4 → 多数決
        for i in range(1, 5):
            if self._has(alt, KeyCode.from_char(str(i))):
                self._pressed.clear()
                choice = i
                threading.Thread(
                    target=lambda n=choice: self._on_vote(n), daemon=True
                ).start()
                return
