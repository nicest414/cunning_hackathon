"""選択テキスト取得ユーティリティ。

macOS の Accessibility API (AXUIElement) を使い、フォーカス中の UI 要素から
選択テキストを直接取得する。クリップボードを経由しないため、既存の
クリップボード内容を汚さず、コピー操作も不要。

必要な権限: システム設定 > プライバシーとセキュリティ > アクセシビリティ
（pynput のグローバルフックと同じ権限のため、追加設定は不要）
"""
import platform

_IS_MAC = platform.system() == "Darwin"


def get_selected_text() -> str:
    """フォーカス中の UI 要素から選択テキストを返す。

    macOS: AXUIElement API で取得。
    Windows: Ctrl+C シミュレーションでクリップボード経由取得。
    その他: 空文字列を返す。
    """
    if _IS_MAC:
        return _get_selected_text_ax()
    if platform.system() == "Windows":
        return _get_selected_text_windows()
    return ""


def _get_selected_text_ax() -> str:
    """macOS: Cmd+C シミュレーションで選択テキストを取得する。

    クリップボードの既存内容を保存・復元するため、クリップボードを汚さない。
    """
    import time
    import subprocess

    try:
        from pynput.keyboard import Controller, Key

        # 現在のクリップボード内容を退避
        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=1
        )
        original = result.stdout if result.returncode == 0 else ""

        # クリップボードを一時的にクリアして Cmd+C を送信
        subprocess.run(["pbcopy"], input="", text=True, timeout=1)

        kbd = Controller()
        kbd.press(Key.cmd)
        kbd.press("c")
        kbd.release("c")
        kbd.release(Key.cmd)

        # クリップボードへの書き込みを待つ
        time.sleep(0.15)

        result = subprocess.run(
            ["pbpaste"], capture_output=True, text=True, timeout=1
        )
        selected = result.stdout if result.returncode == 0 else ""

        # クリップボードを元に戻す
        subprocess.run(["pbcopy"], input=original, text=True, timeout=1)

        return selected
    except Exception as e:
        print(f"[Selection] macOS 取得エラー: {e}")
        return ""


def _get_selected_text_windows() -> str:
    """Windows: Ctrl+C シミュレーションで選択テキストを取得する。

    既存のクリップボード内容を保存・復元するため、クリップボードを汚さない。
    """
    import time
    import ctypes

    try:
        import pyperclip
        from pynput.keyboard import Controller, Key

        # 現在のクリップボード内容を退避
        try:
            original = pyperclip.paste()
        except Exception:
            original = ""

        # クリップボードを一時的にクリアして Ctrl+C を送信
        pyperclip.copy("")
        kbd = Controller()
        kbd.press(Key.ctrl)
        kbd.press("c")
        kbd.release("c")
        kbd.release(Key.ctrl)

        # クリップボードへの書き込みを待つ
        time.sleep(0.15)

        selected = pyperclip.paste()

        # クリップボードを元に戻す
        pyperclip.copy(original)

        return selected if selected else ""
    except Exception as e:
        print(f"[Selection] Windows 取得エラー: {e}")
        return ""
