"""ステルスLED通知 — macOS向け実装。

IOKit / HID API を ctypes 経由で呼び出し、
論理キー状態を変えずにCaps Lock LEDのみを物理制御する。

権限要件: アクセシビリティまたは入力監視権限が必要な場合があります。
"""
from __future__ import annotations

import ctypes
import ctypes.util
import sys
from ctypes import c_int, c_uint32, c_uint64, c_void_p, c_bool

from core.stealth_notifier import AbstractKeyboardLEDNotifier

# ---------------------------------------------------------------------------
# IOKit / CoreFoundation フレームワーク読み込み
# ---------------------------------------------------------------------------

def _load_lib(name: str) -> ctypes.CDLL:
    path = ctypes.util.find_library(name)
    if path is None:
        raise RuntimeError(f"ライブラリが見つかりません: {name}")
    return ctypes.CDLL(path)


try:
    _iokit = _load_lib("IOKit")
    _cf    = _load_lib("CoreFoundation")
    _ax    = _load_lib("ApplicationServices")
except RuntimeError as _e:
    raise RuntimeError(f"macOS フレームワークの読み込み失敗: {_e}") from _e

# ---------------------------------------------------------------------------
# HID定数
# ---------------------------------------------------------------------------

_kIOHIDOptionsTypeNone         = 0
_kIOHIDManagerOptionNone       = 0
_kHIDPage_GenericDesktop       = 0x01  # HID Generic Desktop Controls usage page
_kHIDUsage_GD_Keyboard         = 0x06  # Keyboard usage (Generic Desktop page)
_kHIDUsage_LED_CapsLock        = 0x02  # LED usage: Caps Lock

_kCFRunLoopDefaultMode = None  # 後でCFStringRef取得

# ---------------------------------------------------------------------------
# CoreFoundation ヘルパー
# ---------------------------------------------------------------------------

_cf.CFNumberCreate.restype  = c_void_p
_cf.CFNumberCreate.argtypes = [c_void_p, c_int, ctypes.POINTER(c_uint32)]
_cf.CFDictionaryCreate.restype  = c_void_p
_cf.CFDictionaryCreate.argtypes = [
    c_void_p, ctypes.POINTER(c_void_p), ctypes.POINTER(c_void_p),
    c_int, c_void_p, c_void_p
]
_cf.CFSetGetValues.restype  = None
_cf.CFSetGetValues.argtypes = [c_void_p, ctypes.POINTER(c_void_p)]
_cf.CFSetGetCount.restype   = c_int
_cf.CFSetGetCount.argtypes  = [c_void_p]
_cf.CFArrayGetCount.restype  = ctypes.c_long  # CFIndex = c_long on 64-bit macOS
_cf.CFArrayGetCount.argtypes = [c_void_p]
_cf.CFArrayGetValueAtIndex.restype  = c_void_p
_cf.CFArrayGetValueAtIndex.argtypes = [c_void_p, ctypes.c_long]  # CFIndex = c_long on 64-bit macOS
_cf.CFRetain.restype  = c_void_p
_cf.CFRetain.argtypes = [c_void_p]
_cf.CFRelease.restype  = None
_cf.CFRelease.argtypes = [c_void_p]

# kCFTypeDictionaryKeyCallBacks / kCFTypeDictionaryValueCallBacks
_kCFTypeDictionaryKeyCallBacks   = c_void_p.in_dll(_cf, "kCFTypeDictionaryKeyCallBacks")
_kCFTypeDictionaryValueCallBacks = c_void_p.in_dll(_cf, "kCFTypeDictionaryValueCallBacks")

_cf.CFStringCreateWithCString.restype  = c_void_p
_cf.CFStringCreateWithCString.argtypes = [c_void_p, ctypes.c_char_p, c_uint32]

_kCFStringEncodingUTF8 = 0x08000100

# ---------------------------------------------------------------------------
# IOKit HID
# ---------------------------------------------------------------------------

_iokit.IOHIDManagerCreate.restype  = c_void_p
_iokit.IOHIDManagerCreate.argtypes = [c_void_p, c_uint32]

_iokit.IOHIDManagerSetDeviceMatching.restype  = None
_iokit.IOHIDManagerSetDeviceMatching.argtypes = [c_void_p, c_void_p]

_iokit.IOHIDManagerOpen.restype  = c_int  # IOReturn
_iokit.IOHIDManagerOpen.argtypes = [c_void_p, c_uint32]

_iokit.IOHIDManagerCopyDevices.restype  = c_void_p
_iokit.IOHIDManagerCopyDevices.argtypes = [c_void_p]

_iokit.IOHIDDeviceCopyMatchingElements.restype  = c_void_p
_iokit.IOHIDDeviceCopyMatchingElements.argtypes = [c_void_p, c_void_p, c_uint32]

_iokit.IOHIDElementGetUsagePage.restype  = c_uint32
_iokit.IOHIDElementGetUsagePage.argtypes = [c_void_p]

_iokit.IOHIDElementGetUsage.restype  = c_uint32
_iokit.IOHIDElementGetUsage.argtypes = [c_void_p]

_iokit.IOHIDValueCreateWithIntegerValue.restype  = c_void_p
_iokit.IOHIDValueCreateWithIntegerValue.argtypes = [c_void_p, c_void_p, c_uint64, ctypes.c_long]

_iokit.IOHIDDeviceSetValue.restype  = c_int
_iokit.IOHIDDeviceSetValue.argtypes = [c_void_p, c_void_p, c_void_p]

# ApplicationServices: AXIsProcessTrusted
_ax.AXIsProcessTrusted.restype  = c_bool
_ax.AXIsProcessTrusted.argtypes = []

# ---------------------------------------------------------------------------
# kIOHIDDeviceUsagePageKey / kIOHIDDeviceUsageKey (文字列キー)
# ---------------------------------------------------------------------------

def _cfstr(s: str) -> c_void_p:
    return c_void_p(_cf.CFStringCreateWithCString(None, s.encode(), _kCFStringEncodingUTF8))


def _cfnum(n: int) -> c_void_p:
    val = c_uint32(n)
    kCFNumberIntType = 9  # kCFNumberSInt64Type
    return c_void_p(_cf.CFNumberCreate(None, kCFNumberIntType, ctypes.byref(val)))


def _build_matching_dict(usage_page: int, usage: int) -> c_void_p:
    """HIDデバイスマッチング辞書を作成する。"""
    key_page  = _cfstr("DeviceUsagePage")
    key_usage = _cfstr("DeviceUsage")
    val_page  = _cfnum(usage_page)
    val_usage = _cfnum(usage)

    keys = (c_void_p * 2)(key_page, key_usage)
    vals = (c_void_p * 2)(val_page, val_usage)

    d = _cf.CFDictionaryCreate(
        None, keys, vals, 2,
        ctypes.byref(_kCFTypeDictionaryKeyCallBacks),
        ctypes.byref(_kCFTypeDictionaryValueCallBacks),
    )
    _cf.CFRelease(key_page)
    _cf.CFRelease(key_usage)
    _cf.CFRelease(val_page)
    _cf.CFRelease(val_usage)
    return c_void_p(d)


# ---------------------------------------------------------------------------
# macOS LED Notifier
# ---------------------------------------------------------------------------

class MacOSLEDNotifier(AbstractKeyboardLEDNotifier):
    """IOKit HID APIを経由してCaps Lock LEDを物理制御する。"""

    def __init__(self) -> None:
        super().__init__()
        self._cached_caps_state: bool = False
        self._check_accessibility()
        self._manager, self._devices = self._setup_hid()
        # 初回キャッシュ: __init__ はメインスレッドで呼ばれるため安全
        self.refresh_caps_state()

    def _check_accessibility(self) -> None:
        trusted = bool(_ax.AXIsProcessTrusted())
        if not trusted:
            print(
                "[LED] 警告: アクセシビリティ権限がありません。\n"
                "  システム設定 > プライバシーとセキュリティ > アクセシビリティ に\n"
                "  このターミナル/アプリを追加してください。",
                file=sys.stderr,
            )

    def _setup_hid(self):
        """HIDマネージャーを作成しキーボードデバイスをオープンする。"""
        manager = _iokit.IOHIDManagerCreate(None, _kIOHIDManagerOptionNone)
        if not manager:
            raise RuntimeError("IOHIDManagerCreate 失敗")

        matching = _build_matching_dict(_kHIDPage_GenericDesktop, _kHIDUsage_GD_Keyboard)
        _iokit.IOHIDManagerSetDeviceMatching(manager, matching)
        _cf.CFRelease(matching)

        ret = _iokit.IOHIDManagerOpen(manager, _kIOHIDOptionsTypeNone)
        if ret != 0:
            raise RuntimeError(f"IOHIDManagerOpen 失敗: ret={ret}")

        device_set = _iokit.IOHIDManagerCopyDevices(manager)
        if not device_set:
            raise RuntimeError("キーボードデバイスが見つかりません")

        count = _cf.CFSetGetCount(device_set)
        if count == 0:
            _cf.CFRelease(device_set)
            raise RuntimeError("キーボードデバイスが0件です")

        devices_arr = (c_void_p * count)()
        _cf.CFSetGetValues(device_set, devices_arr)
        _cf.CFRelease(device_set)

        return manager, list(devices_arr)

    def _find_caps_lock_element(self, device: c_void_p):
        """デバイスからCaps Lock LEDエレメントを検索して返す。

        IOHIDDeviceCopyMatchingElements は CFArrayRef を返すため
        CFArray 系の関数を使用する。
        """
        elements = _iokit.IOHIDDeviceCopyMatchingElements(device, None, _kIOHIDOptionsTypeNone)
        if not elements:
            return None

        count = _cf.CFArrayGetCount(elements)
        result = None
        for i in range(count):
            elem = _cf.CFArrayGetValueAtIndex(elements, i)
            if not elem:
                continue
            usage_page = _iokit.IOHIDElementGetUsagePage(elem)
            usage = _iokit.IOHIDElementGetUsage(elem)
            # LED Usage Page = 0x08, Caps Lock = 0x02
            if usage_page == 0x08 and usage == _kHIDUsage_LED_CapsLock:
                result = elem
                _cf.CFRetain(result)  # 配列解放後もポインタを有効に保つ
                break

        _cf.CFRelease(elements)
        return result

    def set_led(self, state: bool) -> None:
        """Caps Lock LEDを直接制御する。"""
        for device in self._devices:
            elem = self._find_caps_lock_element(device)
            if elem is None:
                continue
            value = _iokit.IOHIDValueCreateWithIntegerValue(None, elem, 0, 1 if state else 0)
            if value:
                _iokit.IOHIDDeviceSetValue(device, elem, value)
                _cf.CFRelease(value)
            _cf.CFRelease(elem)  # _find_caps_lock_element でCFRetainした分を解放

    def refresh_caps_state(self) -> None:
        """Carbon API で Caps Lock 状態を読み取りキャッシュする。

        HIToolbox の TSMCurrentKeyboardInputSourceRefCreate はメインスレッド
        専用APIのため、必ずメインスレッド（QTimer コールバック等）から呼ぶこと。
        バックグラウンドスレッドから呼ぶと EXC_BREAKPOINT でクラッシュする。
        """
        try:
            carbon = ctypes.CDLL("/System/Library/Frameworks/Carbon.framework/Carbon")
            carbon.GetCurrentKeyModifiers.restype = c_uint32
            mods = carbon.GetCurrentKeyModifiers()
            # alphaLock = 0x0400
            self._cached_caps_state = bool(mods & 0x0400)
        except Exception:
            pass

    def _get_current_caps_state(self) -> bool:
        """キャッシュ済みの Caps Lock 論理状態を返す（スレッドセーフ）。

        実際の読み取りは refresh_caps_state() がメインスレッドで行う。
        """
        return self._cached_caps_state

    def __del__(self) -> None:
        try:
            if self._manager:
                _cf.CFRelease(self._manager)
        except Exception:
            pass
