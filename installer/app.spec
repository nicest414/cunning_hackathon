# -*- mode: python ; coding: utf-8 -*-
import sys
from pathlib import Path

ROOT = Path(SPECPATH)  # spec ファイルのあるディレクトリ = installer/
PROJECT_ROOT = ROOT.parent  # プロジェクトルート

block_cipher = None

a = Analysis(
    [str(PROJECT_ROOT / 'main.py')],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # assets/ 以下の画像ファイルを全て同梱する
        (str(PROJECT_ROOT / 'assets' / '*.png'),  'assets'),
        (str(PROJECT_ROOT / 'assets' / '*.jpg'),  'assets'),
    ],
    hiddenimports=[
        # keyring: OS バックエンドを明示的に指定（動的ロードのため自動検出されない）
        'keyring.backends',
        'keyring.backends.macOS',        # macOS Keychain
        'keyring.backends.Windows',      # Windows Credential Manager
        'keyring.backends.SecretService', # Linux（念のため）
        'keyring.backends.fail',
        'keyring.backends.null',
        # pynput: バックエンドの明示（macOS/Windows で分かれる）
        'pynput.keyboard._darwin',
        'pynput.keyboard._win32',
        'pynput.mouse._darwin',
        'pynput.mouse._win32',
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
    name='CunningApp',
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
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='CunningApp',
)

# macOS のみ: .app バンドルを生成する
if sys.platform == 'darwin':
    app = BUNDLE(
        coll,
        name='CunningApp.app',
        icon=None,               # アイコンがある場合は 'assets/icon.icns' を指定
        bundle_identifier='com.example.cunningapp',
        info_plist={
            # pynput のグローバルフックに必要なアクセシビリティ権限の説明
            'NSAccessibilityUsageDescription':
                'キーボードショートカットを検知するためにアクセシビリティ権限が必要です。',
            # mss のスクリーンキャプチャに必要な画面収録権限の説明
            'NSScreenCaptureUsageDescription':
                '画面をキャプチャして AI に送信するために画面収録権限が必要です。',
            # Dock やメニューバーにアイコンを表示しない（バックグラウンドアプリ）
            # 必要に応じてコメントアウトして通常アプリとして動作させる
            # 'LSUIElement': True,
        },
    )
