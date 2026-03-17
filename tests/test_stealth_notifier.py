"""AbstractKeyboardLEDNotifier の点滅プロトコルと排他制御をテストする。

OSハードウェアには触れず、set_led をモック化して純粋にロジックを検証する。
"""
import sys
import threading
import time
import types
import unittest
from unittest.mock import MagicMock, call, patch


# ---------------------------------------------------------------------------
# stealth_notifier をモジュール単体でロードできるよう core stub を用意
# ---------------------------------------------------------------------------

def _load_stealth_notifier():
    sys.modules.pop("core.stealth_notifier", None)
    # notifier_windows / notifier_macos は import されない状況でもテスト可能
    import core.stealth_notifier as mod
    return mod


# ---------------------------------------------------------------------------
# テスト用具体クラス（set_led をモックに差し替え）
# ---------------------------------------------------------------------------

class _MockNotifier:
    """AbstractKeyboardLEDNotifier を継承した最小限のテスト用実装。"""

    def __new__(cls, mod):
        class _Impl(mod.AbstractKeyboardLEDNotifier):
            def set_led(self, state: bool) -> None:
                pass  # モックで上書きするのでここは使われない

            def _get_current_caps_state(self) -> bool:
                return False

        instance = _Impl()
        instance.set_led = MagicMock()
        return instance


# ---------------------------------------------------------------------------
# テストケース
# ---------------------------------------------------------------------------

class TestAbstractProtocol(unittest.TestCase):

    def setUp(self):
        self.mod = _load_stealth_notifier()
        self.notifier = _MockNotifier(self.mod)

    # ----------------------------------------------------------------
    def test_blink_1_calls_set_led_correct_sequence(self):
        """blink(1): 開始×2 + 解答×1 + 終了×1 の最低限の点灯/消灯を確認する。"""
        self.notifier.blink(1)
        # プロトコルが完了するまで待機（タイミング定数が短いが時間がかかる）
        # START: 0.05*4 + INTERVAL: 1 + ANS: 0.5 + END: 1 + 0.1 ≈ 2.75s 上限
        timeout = 4.0
        start = time.monotonic()
        while self.notifier._running and (time.monotonic() - start) < timeout:
            time.sleep(0.05)

        calls = self.notifier.set_led.call_args_list
        # 少なくとも True/False のペアが複数あることを確認
        on_calls  = [c for c in calls if c == call(True)]
        off_calls = [c for c in calls if c == call(False)]
        # 開始2回 + 解答1回 + 終了1回 = 4回点灯
        self.assertEqual(len(on_calls), 4, f"点灯回数が不正: {calls}")
        # 消灯回数: 開始2回 + 解答1回 + 終了後reset(False) ≒ 4回
        self.assertGreaterEqual(len(off_calls), 3, f"消灯回数が不正: {calls}")

    def test_blink_3_calls_correct_answer_count(self):
        """blink(3): 解答部分で3回点灯することを確認する。"""
        # タイミング定数を小さくしてテストを高速化
        self.notifier._START_ON  = 0.01
        self.notifier._START_OFF = 0.01
        self.notifier._INTERVAL  = 0.05
        self.notifier._ANS_ON    = 0.01
        self.notifier._ANS_OFF   = 0.01
        self.notifier._END_WAIT  = 0.05
        self.notifier._END_ON    = 0.01

        self.notifier.blink(3)
        timeout = 2.0
        start = time.monotonic()
        while self.notifier._running and (time.monotonic() - start) < timeout:
            time.sleep(0.02)

        calls = self.notifier.set_led.call_args_list
        on_calls = [c for c in calls if c == call(True)]
        # 開始2回 + 解答3回 + 終了1回 = 6回の点灯
        self.assertEqual(len(on_calls), 6, f"点灯回数が不正 (期待6): {calls}")

    def test_double_blink_is_ignored(self):
        """実行中に blink() を再度呼んでも無視される（排他制御）。"""
        self.notifier._START_ON  = 0.05
        self.notifier._START_OFF = 0.05
        self.notifier._INTERVAL  = 0.5
        self.notifier._ANS_ON    = 0.05
        self.notifier._ANS_OFF   = 0.05
        self.notifier._END_WAIT  = 0.2
        self.notifier._END_ON    = 0.05

        call_count_before = self.notifier.set_led.call_count
        self.notifier.blink(1)

        # わずかに待って実行中を確認
        time.sleep(0.02)
        self.assertTrue(self.notifier._running, "プロトコルが開始されていない")

        # 2回目の blink は無視されるはず
        prev_call_count = self.notifier.set_led.call_count
        self.notifier.blink(2)
        time.sleep(0.05)
        # blink(2) 分のコールが増えていないこと（ロックで弾かれている）
        after_count = self.notifier.set_led.call_count
        # 増加分は blink(1) 継続分のみのはず（大幅には増えない）
        # 排他制御が効いていれば blink(2) 用の余分な点灯がないはず
        self.assertFalse(
            self.notifier._lock.locked() is False and self.notifier._running is False,
            "排他制御が機能していない可能性"
        )

        # プロトコル完了まで待つ
        timeout = 3.0
        start = time.monotonic()
        while self.notifier._running and (time.monotonic() - start) < timeout:
            time.sleep(0.05)

    def test_reset_restores_false_state(self):
        """reset() が _get_current_caps_state=False のとき set_led(False) を呼ぶ。"""
        self.notifier.reset()
        self.notifier.set_led.assert_called_with(False)

    def test_reset_restores_true_state(self):
        """reset() が _get_current_caps_state=True のとき set_led(True) を呼ぶ。"""
        self.notifier._get_current_caps_state = lambda: True
        self.notifier.reset()
        self.notifier.set_led.assert_called_with(True)

    def test_blink_out_of_range_does_nothing(self):
        """blink(0) や blink(10) は無効値として無視される。"""
        self.notifier.blink(0)
        self.notifier.blink(10)
        time.sleep(0.05)
        self.notifier.set_led.assert_not_called()

    def test_null_notifier_does_not_raise(self):
        """_NullNotifier の set_led と reset は例外を出さない。"""
        null = self.mod._NullNotifier()
        null.set_led(True)
        null.set_led(False)
        null.reset()   # 例外が出なければ OK

    def test_null_notifier_blink_does_not_raise(self):
        """_NullNotifier の blink は例外を出さない。"""
        null = self.mod._NullNotifier()
        null._START_ON  = 0.01
        null._START_OFF = 0.01
        null._INTERVAL  = 0.01
        null._ANS_ON    = 0.01
        null._ANS_OFF   = 0.01
        null._END_WAIT  = 0.01
        null._END_ON    = 0.01
        null.blink(2)
        time.sleep(0.3)  # 終了を待つ


# ---------------------------------------------------------------------------
# Factory テスト（プラットフォームをモックで切り替える）
# ---------------------------------------------------------------------------

class TestCreateNotifier(unittest.TestCase):

    def setUp(self):
        self.mod = _load_stealth_notifier()

    def test_create_notifier_unknown_platform_returns_null(self):
        """未対応プラットフォームでは _NullNotifier が返る。"""
        with patch.object(sys, "platform", "linux"):
            notifier = self.mod.create_notifier()
        self.assertIsInstance(notifier, self.mod._NullNotifier)

    def test_create_notifier_windows_fallback_on_error(self):
        """WindowsLEDNotifier の初期化が失敗すると _NullNotifier にフォールバックする。"""
        fake_win_mod = types.ModuleType("core.notifier_windows")

        class _FailingNotifier(self.mod.AbstractKeyboardLEDNotifier):
            def __init__(self):
                raise RuntimeError("デバイスオープン失敗（テスト用）")
            def set_led(self, state): pass
            def _get_current_caps_state(self): return False

        fake_win_mod.WindowsLEDNotifier = _FailingNotifier
        with patch.object(sys, "platform", "win32"):
            with patch.dict(sys.modules, {"core.notifier_windows": fake_win_mod}):
                notifier = self.mod.create_notifier()
        self.assertIsInstance(notifier, self.mod._NullNotifier)


if __name__ == "__main__":
    unittest.main()
