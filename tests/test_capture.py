"""Unit tests for core/capture.py — mss は完全にモック化。"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call


def _build_mss_stub():
    """mss / mss.tools の最小スタブモジュールを返す。"""
    mss_mod = types.ModuleType("mss")
    mss_tools_mod = types.ModuleType("mss.tools")
    mss_mod.tools = mss_tools_mod
    return mss_mod, mss_tools_mod


class TestCaptureScreen(unittest.TestCase):
    def setUp(self):
        self.mss_mod, self.mss_tools_mod = _build_mss_stub()
        sys.modules.pop("core.capture", None)
        sys.modules["mss"] = self.mss_mod
        sys.modules["mss.tools"] = self.mss_tools_mod

        import core.capture as capture_mod
        self.capture_mod = capture_mod

    def tearDown(self):
        sys.modules.pop("core.capture", None)
        sys.modules.pop("mss", None)
        sys.modules.pop("mss.tools", None)

    # ------------------------------------------------------------------
    def _make_sct(self, rgb=b"RGBDATA", size=(1920, 1080)):
        """mss コンテキストマネージャーのモックを組み立てる。"""
        sct = MagicMock()
        screenshot = MagicMock()
        screenshot.rgb = rgb
        screenshot.size = size
        sct.monitors = [None, {"left": 0, "top": 0, "width": 1920, "height": 1080}]
        sct.grab.return_value = screenshot

        ctx_manager = MagicMock()
        ctx_manager.__enter__ = MagicMock(return_value=sct)
        ctx_manager.__exit__ = MagicMock(return_value=False)

        self.mss_mod.mss = MagicMock(return_value=ctx_manager)
        return sct, screenshot

    def test_returns_bytes(self):
        """capture_screen() は bytes を返す。"""
        expected_png = b"\x89PNG\r\nfake-data"
        sct, screenshot = self._make_sct()
        self.mss_tools_mod.to_png = MagicMock(return_value=expected_png)

        result = self.capture_mod.capture_screen()
        self.assertIsInstance(result, bytes)
        self.assertEqual(result, expected_png)

    def test_grabs_primary_monitor(self):
        """monitors[1] (プライマリ) を grab() に渡す。"""
        sct, screenshot = self._make_sct()
        self.mss_tools_mod.to_png = MagicMock(return_value=b"png")

        self.capture_mod.capture_screen()

        sct.grab.assert_called_once_with(sct.monitors[1])

    def test_to_png_called_with_rgb_and_size(self):
        """mss.tools.to_png に rgb と size が渡される。"""
        rgb = b"\x00\x01\x02"
        size = (800, 600)
        sct, screenshot = self._make_sct(rgb=rgb, size=size)
        self.mss_tools_mod.to_png = MagicMock(return_value=b"png")

        self.capture_mod.capture_screen()

        self.mss_tools_mod.to_png.assert_called_once_with(rgb, size)

    def test_mss_context_manager_is_closed(self):
        """with ブロックを使うので __exit__ が必ず呼ばれる。"""
        sct, screenshot = self._make_sct()
        self.mss_tools_mod.to_png = MagicMock(return_value=b"png")

        self.capture_mod.capture_screen()

        ctx = self.mss_mod.mss.return_value
        ctx.__exit__.assert_called_once()


if __name__ == "__main__":
    unittest.main()
