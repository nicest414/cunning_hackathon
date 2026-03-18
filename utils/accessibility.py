"""macOS アクセシビリティ権限の確認・誘導ユーティリティ。"""
import platform
import sys


def is_trusted() -> bool:
    """アクセシビリティ権限が付与されているか確認する。macOS 以外は常に True。"""
    if platform.system() != "Darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        lib.AXIsProcessTrusted.restype = ctypes.c_bool
        return bool(lib.AXIsProcessTrusted())
    except Exception:
        return True  # 確認できない場合は続行


def request_trust_prompt() -> bool:
    """アクセシビリティ権限のダイアログをシステムに要求する（macOS 10.9+）。
    権限ダイアログが表示されるが、付与を待機はしない。
    戻り値: 既に信頼済みなら True"""
    if platform.system() != "Darwin":
        return True
    try:
        import ctypes
        import ctypes.util
        lib = ctypes.cdll.LoadLibrary(ctypes.util.find_library("ApplicationServices"))
        lib.AXIsProcessTrustedWithOptions.restype = ctypes.c_bool
        lib.AXIsProcessTrustedWithOptions.argtypes = [ctypes.c_void_p]

        # kAXTrustedCheckOptionPrompt = True でシステムダイアログを出す
        # CoreFoundation を使って CFDictionaryRef を構築する
        cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
        cf.CFStringCreateWithCString.restype = ctypes.c_void_p
        cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
        cf.CFBooleanGetValue.restype = ctypes.c_bool
        cf.CFDictionaryCreate.restype = ctypes.c_void_p

        kCFStringEncodingUTF8 = 0x08000100
        key_str = cf.CFStringCreateWithCString(
            None, b"AXTrustedCheckOptionPrompt", kCFStringEncodingUTF8
        )
        # kCFBooleanTrue のアドレスを取得
        cf_true = ctypes.c_void_p.in_dll(cf, "kCFBooleanTrue")

        keys = (ctypes.c_void_p * 1)(key_str)
        values = (ctypes.c_void_p * 1)(cf_true)
        options = cf.CFDictionaryCreate(None, keys, values, 1, None, None)

        return bool(lib.AXIsProcessTrustedWithOptions(options))
    except Exception:
        return is_trusted()
