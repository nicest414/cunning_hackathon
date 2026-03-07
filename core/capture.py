"""画面キャプチャモジュール (mss使用)"""
import io
import mss
import mss.tools


def capture_screen() -> bytes:
    """プライマリモニター全体をキャプチャし、PNG バイト列を返す。"""
    with mss.mss() as sct:
        monitor = sct.monitors[1]  # 1 = プライマリモニター
        screenshot = sct.grab(monitor)
        png_bytes = mss.tools.to_png(screenshot.rgb, screenshot.size)
    return png_bytes
