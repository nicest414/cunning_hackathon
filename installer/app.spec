# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH)  # spec ファイルのあるディレクトリ = installer/
PROJECT_ROOT = ROOT.parent  # プロジェクトルート

block_cipher = None

# pynput のサブモジュール・データ・バイナリを全て収集する
# （macOS/Windows の動的バックエンドが自動検出されないため）
_pynput_datas, _pynput_binaries, _pynput_hiddenimports = collect_all('pynput')

a = Analysis(
    [str(PROJECT_ROOT / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=_pynput_binaries,
    datas=[
        # assets/ 以下の画像ファイルを全て同梱する
        (str(PROJECT_ROOT / 'assets' / '*.png'),  'assets'),
        (str(PROJECT_ROOT / 'assets' / '*.jpg'),  'assets'),
    ] + _pynput_datas,
    hiddenimports=_pynput_hiddenimports + [
        # keyring: OS バックエンドを明示的に指定（動的ロードのため自動検出されない）
        'keyring.backends',
        'keyring.backends.macOS',        # macOS Keychain
        'keyring.backends.Windows',      # Windows Credential Manager
        'keyring.backends.SecretService', # Linux（念のため）
        'keyring.backends.fail',
        'keyring.backends.null',
        # PyObjC: pynput._darwin が依存する macOS フレームワーク
        # （PyInstaller は動的ロードされる objc モジュールを自動検出できない）
        'objc',
        'AppKit',
        'Quartz',
        'Quartz.CoreGraphics',
        'CoreFoundation',
        # google-genai の内部依存
        'google.genai',
        'google.auth',
        'google.auth.transport.requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 不要な大きなパッケージを除外してサイズを削減
        'tkinter',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='InputMonitor',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI アプリなのでコンソールウィンドウを非表示
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # Windows: タスクマネージャーのプロパティ欄に表示されるバージョン情報を偽装
    version=str(PROJECT_ROOT / 'installer' / 'version_info.txt') if sys.platform == 'win32' else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='InputMonitor',
)

# macOS のみ: .app バンドルを生成する
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='Input Monitor.app',
        icon=None,               # アイコンがある場合は 'assets/icon.icns' を指定
        bundle_identifier='com.apple.accessibility.inputmonitor',
        info_plist={
            # pynput のグローバルフックに必要なアクセシビリティ権限の説明
            'NSAccessibilityUsageDescription':
                'キーボードショートカットを検知するためにアクセシビリティ権限が必要です。',
            # mss のスクリーンキャプチャに必要な画面収録権限の説明
            'NSScreenCaptureUsageDescription':
                '画面をキャプチャして AI に送信するために画面収録権限が必要です。',
            # Dock・メニューバーにアイコンを表示しない（バックグラウンドアプリとして動作）
            'LSUIElement': True,
        },
    )
