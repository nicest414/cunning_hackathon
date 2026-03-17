# Step 4 — PyInstaller spec ファイルの作成

## このステップでやること

PyInstaller でビルドするための設定ファイル `installer/app.spec` を作成する。
このプロジェクト固有の以下の問題を spec で解決する:

- `assets/` 以下の画像ファイルを同梱する
- `pynput` のグローバルフックが PyInstaller のフリーズ環境で動作しない問題を回避する
- `keyring` のバックエンドプラグインが動的ロードのため同梱されない問題を解決する
- `mss` が Windows DPI スケーリング環境で正しく動作するよう設定する

**前提: Step 1〜3 が完了していること。**

---

## 事前準備

```bash
source .venv/bin/activate
pip install pyinstaller
# macOS のみ: create-dmg をインストール（Homebrew）
# brew install create-dmg
```

---

## `installer/` ディレクトリの作成

以下のファイルを新規作成すること:

```
installer/
├── app.spec          # PyInstaller spec（このステップで作成）
├── build_mac.sh      # macOS 用 dmg 生成スクリプト（このステップで作成）
└── installer.iss     # Inno Setup スクリプト（このステップで作成）
```

---

## `installer/app.spec` の仕様

以下の内容で作成すること。
プロジェクトルートからの相対パスで記述されているため、
**spec はプロジェクトルートから実行する**（`pyinstaller installer/app.spec`）。

```python
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
    upx=True,
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
```

---

## `installer/build_mac.sh` の仕様

macOS 環境で `.app` → `.dmg` に変換するシェルスクリプト。

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_NAME="CunningApp"
DIST_DIR="../dist"
DMG_NAME="${APP_NAME}.dmg"

echo "==> .dmg を生成します..."

create-dmg \
  --volname "${APP_NAME}" \
  --window-size 540 380 \
  --icon-size 128 \
  --icon "${APP_NAME}.app" 130 160 \
  --app-drop-link 400 160 \
  "${DIST_DIR}/${DMG_NAME}" \
  "${DIST_DIR}/${APP_NAME}.app"

echo "==> 完了: ${DIST_DIR}/${DMG_NAME}"
```

このファイルに実行権限を付与すること:

```bash
chmod +x installer/build_mac.sh
```

---

## `installer/installer.iss` の仕様

Windows 環境で Inno Setup を使ってインストーラーを生成するスクリプト。
Inno Setup は別途インストールが必要（`winget install JRSoftware.InnoSetup`）。

```ini
[Setup]
AppName=CunningApp
AppVersion=1.0.0
DefaultDirName={autopf}\CunningApp
DefaultGroupName=CunningApp
OutputBaseFilename=CunningApp_Setup
Compression=lzma
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "..\dist\CunningApp\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs

[Icons]
Name: "{group}\CunningApp"; Filename: "{app}\CunningApp.exe"
Name: "{commondesktop}\CunningApp"; Filename: "{app}\CunningApp.exe"

[Run]
Filename: "{app}\CunningApp.exe"; Description: "起動する"; Flags: nowait postinstall skipifsilent
```

---

## ビルドの動作確認（macOS）

```bash
source .venv/bin/activate
# spec を使ってビルド
pyinstaller installer/app.spec --noconfirm

# dist/ に CunningApp.app が生成されることを確認
ls dist/

# .app を直接起動してテスト
open dist/CunningApp.app
```

アプリが起動し、SetupDialog または MainWindow が表示されれば成功。

---

## よくあるビルドエラーと対処

### `ModuleNotFoundError: No module named 'keyring.backends.macOS'`

`hiddenimports` に `'keyring.backends.macOS'` が含まれているか確認する。
含まれていても起きる場合は以下を試す:

```python
# spec の hiddenimports に追加
'jaraco.classes',
'jaraco.text',
'jaraco.functools',
```

### `pynput` がキーを検知しない（ビルド後）

macOS の場合、`.app` を初回起動後に「システム設定 > プライバシーとセキュリティ > アクセシビリティ」に
`CunningApp.app` を追加する必要がある。これはユーザー操作が必要で、自動化はできない。

### `mss` で画面キャプチャに失敗する（Windows）

`main.py` の先頭に以下を追加する（PyInstaller ビルド後も有効）:

```python
import sys
if sys.platform == 'win32':
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
```

---

完了したら `step5_build_script.md` に進むこと。
