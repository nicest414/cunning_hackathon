"""選択テキスト取得ユーティリティ。

Cmd/Ctrl+C シミュレーション＋クリップボード退避/復元を使って、
フォーカス中の UI 要素で選択されているテキストを取得する。
テキスト形式のクリップボード内容は退避・復元するが、画像など非テキスト形式の
データは復元できない点に注意。

必要な権限: システム設定 > プライバシーとセキュリティ > アクセシビリティ
（pynput のグローバルフックと同じ権限のため、追加設定は不要）
"""
import platform

_IS_MAC = platform.system() == "Darwin"


def get_selected_text() -> str:
    """フォーカス中の UI 要素から選択テキストを返す。

    macOS: pbcopy/pbpaste + Cmd+C シミュレーションで取得。
    Windows: clip/powershell + Ctrl+C シミュレーションで取得。
    その他: 空文字列を返す。
    """
    if _IS_MAC:
        return _get_selected_text_macos()
    if platform.system() == "Windows":
        return _get_selected_text_windows()
    return ""


def _get_selected_text_macos() -> str:
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
        selected = ""
        try:
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
        finally:
            # 例外が起きても必ずクリップボードを元に戻す
            subprocess.run(["pbcopy"], input=original, text=True, timeout=1)

        return selected
    except Exception as e:
        print(f"[Selection] macOS 取得エラー: {e}")
        return ""


def _get_selected_text_windows() -> str:
    """Windows: Ctrl+C シミュレーションで選択テキストを取得する。

    既存のクリップボード内容を保存・復元するため、クリップボードを汚さない。
    clip コマンドと powershell Get-Clipboard を使用し、外部ライブラリ不要。
    """
    import time
    import subprocess

    try:
        from pynput.keyboard import Controller, Key

        # 現在のクリップボード内容を退避
        result = subprocess.run(
            ["powershell", "-command", "Get-Clipboard"],
            capture_output=True, text=True, timeout=2,
        )
        original = result.stdout.rstrip("\n") if result.returncode == 0 else ""

        # クリップボードを一時的にクリアして Ctrl+C を送信
        subprocess.run(["clip"], input="", text=True, timeout=1)
        selected = ""
        try:
            kbd = Controller()
            kbd.press(Key.ctrl)
            kbd.press("c")
            kbd.release("c")
            kbd.release(Key.ctrl)

            # クリップボードへの書き込みを待つ
            time.sleep(0.15)

            result = subprocess.run(
                ["powershell", "-command", "Get-Clipboard"],
                capture_output=True, text=True, timeout=2,
            )
            selected = result.stdout.rstrip("\n") if result.returncode == 0 else ""
        finally:
            # 例外が起きても必ずクリップボードを元に戻す
            subprocess.run(["clip"], input=original, text=True, timeout=1)

        return selected
    except Exception as e:
        print(f"[Selection] Windows 取得エラー: {e}")
        return ""
