"""ステルスLED通知 — 共通インターフェースと点滅プロトコル。

仕様書: docs/stealth_led_spec.md
"""
from __future__ import annotations

import sys
import threading
import time
from abc import ABC, abstractmethod


class AbstractKeyboardLEDNotifier(ABC):
    """キーボードLEDを用いたステルス通知の抽象基底クラス。

    サブクラスは `set_led(state: bool)` のみ実装すればよい。
    点滅プロトコル（開始シグナル → 解答 → 終了シグナル → リセット）は
    このクラスが担当し、専用スレッドで非同期実行される。
    """

    # ---- 伝達プロトコルのタイミング定数 (仕様書 §4) ----
    _START_ON  = 0.05   # 開始シグナル: 点灯0.05秒
    _START_OFF = 0.05   # 開始シグナル: 消灯0.05秒
    _START_COUNT = 2    # 開始シグナル: 2回点滅
    _INTERVAL  = 1.0    # インターバル: 1秒消灯
    _ANS_ON    = 0.3    # 解答点滅: 点灯0.3秒
    _ANS_OFF   = 0.2    # 解答点滅: 消灯0.2秒
    _END_WAIT  = 1.0    # 終了前消灯: 1秒
    _END_ON    = 0.1    # 終了シグナル: 点灯0.1秒

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._running = False
        self._cancel_event = threading.Event()

    # ---- サブクラスが実装するメソッド ----

    @abstractmethod
    def set_led(self, state: bool) -> None:
        """Caps Lock LEDを物理的に制御する（論理キー状態は変更しない）。

        Args:
            state: True = 点灯 / False = 消灯
        """
        ...

    @abstractmethod
    def _get_current_caps_state(self) -> bool:
        """現在のOSが認識しているCaps Lockの論理状態を返す。"""
        ...

    # ---- 公開 API ----

    def blink(self, count: int) -> None:
        """点滅プロトコルを非同期スレッドで実行する。

        既にプロトコルが実行中の場合は無視する（排他制御）。

        Args:
            count: 答えの数字に対応する点滅回数（1〜4）
        """
        if not (1 <= count <= 9):
            return

        # 排他制御: 実行中なら無視
        if not self._lock.acquire(blocking=False):
            return

        self._cancel_event.clear()
        self._running = True
        t = threading.Thread(
            target=self._run_protocol,
            args=(count,),
            daemon=True,
            name="stealth-led",
        )
        t.start()

    def reset(self) -> None:
        """OSの論理Caps Lock状態に合わせてLEDを復元する。"""
        try:
            self.set_led(self._get_current_caps_state())
        except Exception as e:
            print(f"[LED] reset() failed: {e}", file=sys.stderr)

    def cancel(self) -> None:
        """実行中のプロトコルをキャンセルし、LEDをリセットする。"""
        self._cancel_event.set()

    def refresh_caps_state(self) -> None:
        """Caps Lock の論理状態をメインスレッドで読み取りキャッシュする。

        PyQt6 の QTimer などから定期的に呼び出すこと（メインスレッド限定）。
        デフォルト実装は何もしない。macOS サブクラスでオーバーライドする。
        """

    def notify_accepted(self) -> None:
        """クリップボード置換のリクエストを受理したことを通知する（1回点灯）。"""
        if not self._lock.acquire(blocking=False):
            return

        self._cancel_event.clear()
        self._running = True

        def _run() -> None:
            try:
                self.set_led(True)
                if self._sleep(0.5):
                    return
                self.set_led(False)
            except Exception as e:
                # LED制御の失敗はステルス性を優先して握りつぶし、
                # 最小限の情報のみstderrに出力する
                print(f"[LED] notify_accepted() failed: {e}", file=sys.stderr)
            finally:
                self.reset()
                self._running = False
                self._lock.release()

        t = threading.Thread(target=_run, daemon=True, name="stealth-led-accept")
        t.start()

    def notify_ready(self) -> None:
        """クリップボード置換の準備が完了したことを通知する（2回短く点滅）。"""
        # 即時にロックを取れない場合は、進行中の通知をキャンセルして
        # 短時間だけロック取得を待つ。これにより「受理 → 準備完了」の
        # 順序付き通知が高い確率で保証される。
        if not self._lock.acquire(blocking=False):
            # すでに別の通知シーケンスが走っている想定なので、まずキャンセルを要求
            try:
                self.cancel()
            except Exception:
                # ステルス性重視のため、ここでの失敗は黙って諦める
                return

            # キャンセル要求後、短いタイムアウト付きでロック再取得を試みる
            try:
                acquired: bool = self._lock.acquire(timeout=0.3)
            except TypeError:
                # 古いPythonなどで timeout 引数がサポートされない場合のフォールバック
                # この場合はこれ以上ブロックせずに諦める
                return
            except Exception:
                # 予期せぬ例外もステルス性を優先して握りつぶす
                return

            if not acquired:
                # 短時間待ってもロックが取れない場合は通知を諦める
                return

        self._cancel_event.clear()
        self._running = True

        def _run() -> None:
            try:
                for _ in range(2):
                    self.set_led(True)
                    if self._sleep(0.1):
                        return
                    self.set_led(False)
                    if self._sleep(0.1):
                        return
            finally:
                self.reset()
                self._running = False
                self._lock.release()

        t = threading.Thread(target=_run, daemon=True, name="stealth-led-ready")
        t.start()

    # ---- 内部実装 ----

    def _sleep(self, seconds: float) -> bool:
        """キャンセル可能なスリープ。キャンセルされた場合 True を返す。"""
        return self._cancel_event.wait(timeout=seconds)

    def _run_protocol(self, count: int) -> None:
        """点滅プロトコル本体。ロックを保持したまま実行され、終了時に解放する。"""
        try:
            # 1. 開始シグナル: 高速点滅 × _START_COUNT 回
            for _ in range(self._START_COUNT):
                self.set_led(True)
                if self._sleep(self._START_ON):
                    return
                self.set_led(False)
                if self._sleep(self._START_OFF):
                    return

            # 2. インターバル
            if self._sleep(self._INTERVAL):
                return

            # 3. 解答の伝達: ゆっくり count 回点滅
            for _ in range(count):
                self.set_led(True)
                if self._sleep(self._ANS_ON):
                    return
                self.set_led(False)
                if self._sleep(self._ANS_OFF):
                    return

            # 4. 終了シグナル
            if self._sleep(self._END_WAIT):
                return
            self.set_led(True)
            if self._sleep(self._END_ON):
                return
            self.set_led(False)

        except Exception as e:
            print(f"[LED] プロトコル実行エラー: {e}", file=sys.stderr)
        finally:
            # 5. リセット: 必ず元の論理状態に戻す
            self.reset()
            self._running = False
            self._lock.release()


# ---------------------------------------------------------------------------
# No-op フォールバック
# ---------------------------------------------------------------------------

class _NullNotifier(AbstractKeyboardLEDNotifier):
    """LED操作が利用できない環境向けの何もしない実装。"""

    def set_led(self, state: bool) -> None:
        pass  # 何もしない

    def _get_current_caps_state(self) -> bool:
        return False


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_notifier() -> AbstractKeyboardLEDNotifier:
    """実行環境に応じた `AbstractKeyboardLEDNotifier` を返す。

    - Windows → `notifier_windows.WindowsLEDNotifier`
    - macOS   → `notifier_macos.MacOSLEDNotifier`
    - その他  → `_NullNotifier`（何もしない）

    デバイスアクセスに失敗した場合も `_NullNotifier` にフォールバックし、
    アプリをクラッシュさせない。
    """
    platform = sys.platform

    if platform == "win32":
        try:
            from core.notifier_windows import WindowsLEDNotifier
            notifier = WindowsLEDNotifier()
            print("[LED] Windows LED notifier を初期化しました。")
            return notifier
        except Exception as e:
            print(f"[LED] Windows notifier の初期化に失敗 (フォールバック): {e}", file=sys.stderr)

    elif platform == "darwin":
        try:
            from core.notifier_macos import MacOSLEDNotifier
            notifier = MacOSLEDNotifier()
            print("[LED] macOS LED notifier を初期化しました。")
            return notifier
        except Exception as e:
            print(f"[LED] macOS notifier の初期化に失敗 (フォールバック): {e}", file=sys.stderr)

    else:
        print(f"[LED] 未対応プラットフォーム ({platform})。LED通知は無効化されます。", file=sys.stderr)

    return _NullNotifier()
