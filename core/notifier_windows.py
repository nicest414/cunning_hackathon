"""ステルスLED通知 — Windows向け実装。

DeviceIoControl + IOCTL_KEYBOARD_SET_INDICATORS を用いて
論理キー状態を変えずにCaps Lock LEDのみを物理制御する。
"""
from __future__ import annotations

import ctypes
import ctypes.wintypes
import sys
from ctypes import wintypes

from core.stealth_notifier import AbstractKeyboardLEDNotifier

# ---------------------------------------------------------------------------
# WinAPI 定数・構造体
# ---------------------------------------------------------------------------

# GENERIC_READ | GENERIC_WRITE
_GENERIC_READ  = 0x80000000
_GENERIC_WRITE = 0x40000000

_FILE_SHARE_READ  = 0x00000001
_FILE_SHARE_WRITE = 0x00000002

_OPEN_EXISTING = 3

# FILE_ATTRIBUTE_NORMAL
_FILE_ATTRIBUTE_NORMAL = 0x80

# IOCTL_KEYBOARD_SET_INDICATORS
# CTL_CODE(FILE_DEVICE_KEYBOARD=0x000b, 0x0002, METHOD_BUFFERED=0, FILE_ANY_ACCESS=0)
# = (0x000b << 16) | (0x0002 << 2) | 0 | 0  = 0x000b0008
_IOCTL_KEYBOARD_SET_INDICATORS = 0x000b0008

# IOCTL_KEYBOARD_QUERY_INDICATORS
_IOCTL_KEYBOARD_QUERY_INDICATORS = 0x000b0100

# LED フラグ
_KEYBOARD_CAPS_LOCK_ON   = 0x0004
_KEYBOARD_NUM_LOCK_ON    = 0x0002
_KEYBOARD_SCROLL_LOCK_ON = 0x0001

_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


class _KEYBOARD_INDICATOR_PARAMETERS(ctypes.Structure):
    """KEYBOARD_INDICATOR_PARAMETERS 構造体。"""
    _fields_ = [
        ("UnitId",         wintypes.USHORT),
        ("LedFlags",       wintypes.USHORT),
    ]


# ---------------------------------------------------------------------------
# Windows LED Notifier
# ---------------------------------------------------------------------------

class WindowsLEDNotifier(AbstractKeyboardLEDNotifier):
    """DeviceIoControl でキーボードドライバに直接LEDを制御する。"""

    # 試みるデバイスパス一覧（NT名前空間への直接アクセス）
    _DEVICE_PATHS = [
        r"\\?\GLOBALROOT\Device\KeyboardClass0",
        r"\\?\GLOBALROOT\Device\KeyboardClass1",
        r"\\?\GLOBALROOT\Device\KeyboardClass2",
        r"\\.\KeyboardClass0",
        r"\\.\KeyboardClass1",
    ]

    def __init__(self) -> None:
        super().__init__()
        self._handle = self._open_device()

    # ---- デバイスオープン ----

    def _open_device(self) -> wintypes.HANDLE:
        """キーボードデバイスへのハンドルを取得する。失敗時は RuntimeError。"""
        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        
        # 戻り値の型を明示しないと 64ビット環境でポインタが切り詰められ無効なハンドルになる
        kernel32.CreateFileW.restype = wintypes.HANDLE
        kernel32.CreateFileW.argtypes = [
            wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE
        ]

        for path in self._DEVICE_PATHS:
            handle = kernel32.CreateFileW(
                path,
                _GENERIC_WRITE,  # READ権限を要求するとSharing Violationになることが多い
                _FILE_SHARE_READ | _FILE_SHARE_WRITE,  # 共有アクセスを許可してキーボードフックと共存させる
                None,
                _OPEN_EXISTING,
                _FILE_ATTRIBUTE_NORMAL,
                None,
            )
            if handle and handle != _INVALID_HANDLE_VALUE:
                return handle

        raise RuntimeError(
            "キーボードデバイスをオープンできませんでした。"
            "管理者権限で起動してください。"
        )

    # ---- LED 制御 ----

    def set_led(self, state: bool) -> None:
        """Caps Lock LEDの物理状態を変更する（論理状態には触れない）。"""
        params = _KEYBOARD_INDICATOR_PARAMETERS()
        params.UnitId = 0
        params.LedFlags = _KEYBOARD_CAPS_LOCK_ON if state else 0

        bytes_returned = wintypes.DWORD(0)
        ok = ctypes.windll.kernel32.DeviceIoControl(  # type: ignore[attr-defined]
            self._handle,
            _IOCTL_KEYBOARD_SET_INDICATORS,
            ctypes.byref(params),
            ctypes.sizeof(params),
            None,
            0,
            ctypes.byref(bytes_returned),
            None,
        )
        if not ok:
            err = ctypes.GetLastError()
            raise OSError(f"DeviceIoControl 失敗: error={err}")

    def _get_current_caps_state(self) -> bool:
        """GetKeyState で現在の論理Caps Lock状態を返す。"""
        VK_CAPITAL = 0x14
        state = ctypes.windll.user32.GetKeyState(VK_CAPITAL)  # type: ignore[attr-defined]
        # 最下位ビットが1ならCaps Lock ON
        return bool(state & 0x0001)

    def __del__(self) -> None:
        """クリーンアップ時にデバイスハンドルを閉じる。"""
        try:
            if self._handle and self._handle != _INVALID_HANDLE_VALUE:
                ctypes.windll.kernel32.CloseHandle(self._handle)  # type: ignore[attr-defined]
        except Exception:
            pass
