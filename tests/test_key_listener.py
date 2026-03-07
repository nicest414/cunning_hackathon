"""Unit tests for utils/key_listener.py — pynput はモック化して OS フックを起動しない。"""
import sys
import types
import unittest
from unittest.mock import MagicMock, patch, call


def _build_pynput_stub():
    """pynput の最小スタブモジュールを組み立てる。"""
    pynput_mod = types.ModuleType("pynput")
    keyboard_mod = types.ModuleType("pynput.keyboard")

    class _Key:
        cmd = "cmd"
        ctrl = "ctrl"
        shift = "shift"
        alt = "alt"
        space = "space"

    class _KeyCode:
        def __init__(self, char=None):
            self.char = char

        @classmethod
        def from_char(cls, c):
            return cls(char=c)

        def __eq__(self, other):
            if isinstance(other, _KeyCode):
                return self.char == other.char
            return False

        def __hash__(self):
            return hash(self.char)

    keyboard_mod.Key = _Key
    keyboard_mod.KeyCode = _KeyCode
    keyboard_mod.Listener = MagicMock()

    pynput_mod.keyboard = keyboard_mod
    return pynput_mod, keyboard_mod


class TestKeyListener(unittest.TestCase):
    def setUp(self):
        self.pynput_mod, self.keyboard_mod = _build_pynput_stub()

        sys.modules.pop("utils.key_listener", None)
        sys.modules["pynput"] = self.pynput_mod
        sys.modules["pynput.keyboard"] = self.keyboard_mod

        import utils.key_listener as kl_mod
        self.kl_mod = kl_mod
        self.Key = self.keyboard_mod.Key
        self.KeyCode = self.keyboard_mod.KeyCode

    def tearDown(self):
        sys.modules.pop("utils.key_listener", None)
        sys.modules.pop("pynput", None)
        sys.modules.pop("pynput.keyboard", None)

    def _make_listener(self, on_ai_answer=None, on_vote=None, on_panic=None):
        return self.kl_mod.KeyListener(
            on_ai_answer=on_ai_answer or MagicMock(),
            on_vote=on_vote or MagicMock(),
            on_panic=on_panic or MagicMock(),
        )

    # ------------------------------------------------------------------
    def test_start_creates_pynput_listener(self):
        """start() が keyboard.Listener を生成し start() を呼ぶ。"""
        kl = self._make_listener()
        kl.start()

        self.keyboard_mod.Listener.assert_called_once()
        mock_listener_instance = self.keyboard_mod.Listener.return_value
        mock_listener_instance.start.assert_called_once()

    def test_stop_calls_listener_stop(self):
        """stop() が内部リスナーの stop() を呼ぶ。"""
        kl = self._make_listener()
        kl.start()
        kl.stop()

        mock_listener_instance = self.keyboard_mod.Listener.return_value
        mock_listener_instance.stop.assert_called_once()
        self.assertIsNone(kl._listener)

    def test_on_press_adds_key_to_pressed(self):
        """_on_press() でキーが _pressed セットに追加される。"""
        kl = self._make_listener()
        kl._on_press(self.Key.shift)
        self.assertIn(self.Key.shift, kl._pressed)

    def test_on_release_removes_key_from_pressed(self):
        """_on_release() でキーが _pressed セットから除去される。"""
        kl = self._make_listener()
        kl._pressed.add(self.Key.shift)
        kl._on_release(self.Key.shift)
        self.assertNotIn(self.Key.shift, kl._pressed)

    def test_has_returns_true_when_all_keys_pressed(self):
        """_has() は指定キーがすべて押されていると True を返す。"""
        kl = self._make_listener()
        kl._pressed = {self.Key.cmd, self.Key.shift}
        self.assertTrue(kl._has(self.Key.cmd, self.Key.shift))

    def test_has_returns_false_when_key_missing(self):
        """_has() はひとつでも欠けると False を返す。"""
        kl = self._make_listener()
        kl._pressed = {self.Key.cmd}
        self.assertFalse(kl._has(self.Key.cmd, self.Key.shift))

    def test_hotkey_ai_answer_fires_callback(self):
        """Mod+Shift+Space が押されると on_ai_answer が呼ばれる。"""
        on_ai_answer = MagicMock()
        kl = self._make_listener(on_ai_answer=on_ai_answer)

        mod = self.kl_mod._MOD_KEY
        kl._pressed = {mod, self.Key.shift, self.Key.space}
        kl._check_hotkeys()

        # スレッドが完了するまで少し待つ
        import time; time.sleep(0.05)
        on_ai_answer.assert_called_once()

    def test_hotkey_panic_fires_callback(self):
        """Mod+Shift+Q が押されると on_panic が呼ばれる。"""
        on_panic = MagicMock()
        kl = self._make_listener(on_panic=on_panic)

        mod = self.kl_mod._MOD_KEY
        kl._pressed = {mod, self.Key.shift, self.KeyCode.from_char("q")}
        kl._check_hotkeys()

        import time; time.sleep(0.05)
        on_panic.assert_called_once()

    def test_hotkey_vote_fires_callback_with_correct_number(self):
        """Alt+N が押されると on_vote(N) が呼ばれる (N=1〜4)。"""
        for i in range(1, 5):
            on_vote = MagicMock()
            kl = self._make_listener(on_vote=on_vote)

            kl._pressed = {self.Key.alt, self.KeyCode.from_char(str(i))}
            kl._check_hotkeys()

            import time; time.sleep(0.05)
            on_vote.assert_called_once_with(i)

    def test_hotkey_clears_pressed_after_trigger(self):
        """ホットキー発火後、_pressed がクリアされて連続発火しない。"""
        kl = self._make_listener()
        mod = self.kl_mod._MOD_KEY
        kl._pressed = {mod, self.Key.shift, self.Key.space}
        kl._check_hotkeys()

        self.assertEqual(len(kl._pressed), 0)

    def test_no_callback_when_no_hotkey_matched(self):
        """ホットキーが揃っていない場合、コールバックは呼ばれない。"""
        on_ai_answer = MagicMock()
        on_vote = MagicMock()
        on_panic = MagicMock()
        kl = self._make_listener(on_ai_answer=on_ai_answer, on_vote=on_vote, on_panic=on_panic)

        kl._pressed = {self.Key.shift}
        kl._check_hotkeys()

        import time; time.sleep(0.05)
        on_ai_answer.assert_not_called()
        on_vote.assert_not_called()
        on_panic.assert_not_called()


if __name__ == "__main__":
    unittest.main()
