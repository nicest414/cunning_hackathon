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
_WINDOWS_PRE_COPY_DELAY_SEC = 0.12
_WINDOWS_CLIPBOARD_SETTLE_SEC = 0.2
_WINDOWS_COPY_RETRY_DELAYS_SEC = (0.12, 0.2, 0.35)


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

    注意: pbpaste/pbcopy はメインスレッド以外からも呼び出し可能だが、
    PyInstaller ビルド版 .app からは動作しない場合がある。
    ビルド版での macOS クリップボード操作は main.py の _do_copy_hijack で
    Qt clipboard + QTimer を使ってメインスレッドから行うこと。
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
            # ホットキー押下直後は Shift が残っていることがあるため、少し待って競合を避ける
            time.sleep(_WINDOWS_PRE_COPY_DELAY_SEC)
            kbd = Controller()
            shift_keys = [
                Key.shift,
                getattr(Key, "shift_l", None),
                getattr(Key, "shift_r", None),
            ]
            for shift_key in shift_keys:
                if shift_key is None:
                    continue
                try:
                    kbd.release(shift_key)
                except Exception:
                    pass
            for delay_sec in _WINDOWS_COPY_RETRY_DELAYS_SEC:
                kbd.press(Key.ctrl)
                kbd.press("c")
                kbd.release("c")
                kbd.release(Key.ctrl)

                # クリップボードへの書き込みを待つ（アプリ差による遅延を吸収）
                time.sleep(delay_sec)

                result = subprocess.run(
                    ["powershell", "-command", "Get-Clipboard"],
                    capture_output=True, text=True, timeout=2,
                )
                selected = result.stdout.rstrip("\r\n") if result.returncode == 0 else ""
                if selected:
                    break

            # 旧定数は残すが、互換維持のため最終待機を入れてタイミング差を抑える
            if not selected:
                time.sleep(_WINDOWS_CLIPBOARD_SETTLE_SEC)
        finally:
            # 例外が起きても必ずクリップボードを元に戻す
            subprocess.run(["clip"], input=original, text=True, timeout=1)

        return selected
    except Exception as e:
        print(f"[Selection] Windows 取得エラー: {e}")
        return ""
