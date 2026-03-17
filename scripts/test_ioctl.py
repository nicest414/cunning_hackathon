import ctypes
from ctypes import wintypes
k32 = ctypes.windll.kernel32
k32.CreateFileW.restype = wintypes.HANDLE

class PA(ctypes.Structure):
    _fields_ = [('i', wintypes.USHORT), ('f', wintypes.USHORT)]

# GENERIC_WRITE (0x40000000) でオープン
path = r'\\?\GLOBALROOT\Device\KeyboardClass0'
h = k32.CreateFileW(path, 0x40000000, 0, None, 3, 0x80, None)
print(f"Path: {path}")
print(f"  Handle: {h}, LastError: {ctypes.GetLastError()}")

if h and h != wintypes.HANDLE(-1).value and h != 18446744073709551615:
    p_struct = PA(0, 4) # CapsLock On
    ret = wintypes.DWORD(0)
    ok = k32.DeviceIoControl(h, 0x000b0008, ctypes.byref(p_struct), 4, None, 0, ctypes.byref(ret), None)
    print(f"  IOCTL: {ok}, LastError: {ctypes.GetLastError()}")
    k32.CloseHandle(h)
