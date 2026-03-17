"""Unit tests for utils/selection.py — subprocess と pynput はモック化する。"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call


def _build_pynput_stub():
    pynput_mod = types.ModuleType("pynput")
    keyboard_mod = types.ModuleType("pynput.keyboard")

    class _Key:
        cmd = "cmd"
        ctrl = "ctrl"

    keyboard_mod.Key = _Key
    keyboard_mod.Controller = MagicMock

    pynput_mod.keyboard = keyboard_mod
    return pynput_mod, keyboard_mod


class TestGetSelectedTextMacOS(unittest.TestCase):
    def setUp(self):
        self.pynput_mod, self.keyboard_mod = _build_pynput_stub()
        sys.modules["pynput"] = self.pynput_mod
        sys.modules["pynput.keyboard"] = self.keyboard_mod
        sys.modules.pop("utils.selection", None)

    def tearDown(self):
        sys.modules.pop("utils.selection", None)
        sys.modules.pop("pynput", None)
        sys.modules.pop("pynput.keyboard", None)

    def _import(self):
        import utils.selection as sel
        return sel

    @patch("platform.system", return_value="Darwin")
    def test_returns_selected_text_on_success(self, _mock_platform):
        """正常系: 選択テキストが取得できる。"""
        sel = self._import()

        def _fake_run(cmd, **kwargs):
            result = MagicMock()
            result.returncode = 0
            if cmd == ["pbpaste"]:
                # 1回目はオリジナル退避、2回目は選択テキスト
                result.stdout = "original" if not hasattr(_fake_run, "_called") else "hello"
                _fake_run._called = True
            else:
                result.stdout = ""
            return result

        with patch("subprocess.run", side_effect=_fake_run), \
             patch("time.sleep"):
            # pbpaste が2回呼ばれることを確認するため side_effect を順番指定
            import subprocess
            mock_run = MagicMock(side_effect=[
                MagicMock(returncode=0, stdout="original"),  # pbpaste (退避)
                MagicMock(returncode=0),                     # pbcopy  (クリア)
                MagicMock(returncode=0, stdout="hello"),     # pbpaste (取得)
                MagicMock(returncode=0),                     # pbcopy  (復元)
            ])
            with patch("subprocess.run", mock_run), patch("time.sleep"):
                result = sel._get_selected_text_macos()

        self.assertEqual(result, "hello")

    @patch("platform.system", return_value="Darwin")
    def test_returns_empty_when_nothing_selected(self, _mock_platform):
        """選択なし（pbpaste が空を返す）→ 空文字列。"""
        sel = self._import()

        mock_run = MagicMock(side_effect=[
            MagicMock(returncode=0, stdout="original"),  # pbpaste (退避)
            MagicMock(returncode=0),                     # pbcopy  (クリア)
            MagicMock(returncode=0, stdout=""),          # pbpaste (取得 → 空)
            MagicMock(returncode=0),                     # pbcopy  (復元)
        ])
        with patch("subprocess.run", mock_run), patch("time.sleep"):
            result = sel._get_selected_text_macos()

        self.assertEqual(result, "")

    @patch("platform.system", return_value="Darwin")
    def test_clipboard_restored_on_exception(self, _mock_platform):
        """途中で例外が起きても pbcopy で復元が呼ばれる。"""
        sel = self._import()

        restore_calls = []

        def _fake_run(cmd, **kwargs):
            if cmd == ["pbpaste"]:
                return MagicMock(returncode=0, stdout="original")
            if cmd == ["pbcopy"] and kwargs.get("input") == "original":
                restore_calls.append(True)
                return MagicMock(returncode=0)
            if cmd == ["pbcopy"] and kwargs.get("input") == "":
                return MagicMock(returncode=0)
            raise RuntimeError("unexpected command")

        # Controller().press() で例外を起こす
        broken_kbd = MagicMock()
        broken_kbd.press.side_effect = RuntimeError("kbd error")

        with patch("subprocess.run", side_effect=_fake_run), \
             patch("time.sleep"), \
             patch("pynput.keyboard.Controller", return_value=broken_kbd):
            result = sel._get_selected_text_macos()

        self.assertEqual(result, "")
        self.assertTrue(len(restore_calls) > 0, "クリップボードが復元されていない")

    @patch("platform.system", return_value="Darwin")
    def test_returns_empty_on_import_error(self, _mock_platform):
        """pynput が import できない場合 → 空文字列。"""
        sel = self._import()

        with patch.dict(sys.modules, {"pynput.keyboard": None}):
            # ImportError を起こすため pynput.keyboard を None にする
            saved = sys.modules.get("pynput.keyboard")
            sys.modules["pynput.keyboard"] = None
            try:
                result = sel._get_selected_text_macos()
            finally:
                sys.modules["pynput.keyboard"] = saved

        self.assertEqual(result, "")


class TestGetSelectedTextDispatch(unittest.TestCase):
    def setUp(self):
        self.pynput_mod, self.keyboard_mod = _build_pynput_stub()
        sys.modules["pynput"] = self.pynput_mod
        sys.modules["pynput.keyboard"] = self.keyboard_mod
        sys.modules.pop("utils.selection", None)

    def tearDown(self):
        sys.modules.pop("utils.selection", None)
        sys.modules.pop("pynput", None)
        sys.modules.pop("pynput.keyboard", None)

    def test_dispatches_to_macos_on_darwin(self):
        """Darwin では _get_selected_text_macos が呼ばれる。"""
        with patch("platform.system", return_value="Darwin"):
            import utils.selection as sel
            with patch.object(sel, "_get_selected_text_macos", return_value="mac") as mock_mac:
                result = sel.get_selected_text()
        self.assertEqual(result, "mac")
        mock_mac.assert_called_once()

    def test_dispatches_to_windows(self):
        """Windows では _get_selected_text_windows が呼ばれる。"""
        with patch("platform.system", return_value="Windows"):
            sys.modules.pop("utils.selection", None)
            import utils.selection as sel
            with patch.object(sel, "_get_selected_text_windows", return_value="win") as mock_win, \
                 patch.object(sel, "_IS_MAC", False):
                result = sel.get_selected_text()
        self.assertEqual(result, "win")
        mock_win.assert_called_once()

    def test_returns_empty_on_linux(self):
        """Linux（Darwin でも Windows でもない）→ 空文字列。"""
        with patch("platform.system", return_value="Linux"):
            sys.modules.pop("utils.selection", None)
            import utils.selection as sel
            with patch.object(sel, "_IS_MAC", False):
                result = sel.get_selected_text()
        self.assertEqual(result, "")


if __name__ == "__main__":
    unittest.main()
