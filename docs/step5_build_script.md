# Step 5 — `build.py` の実装（OS自動判定ビルドスクリプト）

## このステップでやること

`python build.py` を実行するだけで、実行環境（macOS / Windows）を自動判定し、
それぞれの配布用パッケージを生成する `build.py` をプロジェクトルートに作成する。

**前提: Step 4（`installer/app.spec` 等）が完了していること。**

---

## `build.py` の仕様

### 実行方法

```bash
# macOS → dist/CunningApp.dmg を生成
source .venv/bin/activate
python build.py

# Windows → dist/CunningApp_Setup.exe を生成
.venv\Scripts\activate
python build.py

# ビルドのみ（パッケージ化をスキップ）
python build.py --skip-package
```

### 処理フロー

```
python build.py
  │
  ├─ pyinstaller のインストール確認（未インストールなら自動 pip install）
  │
  ├─ pyinstaller installer/app.spec --noconfirm を実行
  │   → dist/CunningApp/ (全OS共通)
  │   → dist/CunningApp.app (macOS のみ)
  │
  ├─ darwin の場合:
  │   create-dmg の存在確認（なければエラーメッセージと brew コマンドを表示して終了）
  │   installer/build_mac.sh を実行
  │   → dist/CunningApp.dmg
  │
  └─ win32 の場合:
      ISCC.exe (Inno Setup Compiler) の存在確認（なければエラーと winget コマンドを表示して終了）
      ISCC.exe installer/installer.iss を実行
      → dist/CunningApp_Setup.exe
```

### コードの実装仕様

以下の構造で実装すること。関数に分割し、各処理を明確に分離すること。

```python
"""OS自動判定ビルドスクリプト。"""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent
DIST = ROOT / "dist"


def _run(cmd: list[str], cwd: Path | None = None) -> None:
    """コマンドを実行し、失敗したら SystemExit を raise する。"""
    print(f"$ {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=cwd)
    if result.returncode != 0:
        print(f"[ERROR] コマンドが失敗しました (returncode={result.returncode})")
        sys.exit(result.returncode)


def ensure_pyinstaller() -> None:
    """pyinstaller がインストールされていなければ pip install する。"""
    if shutil.which("pyinstaller") is None:
        print("[INFO] pyinstaller が見つかりません。インストールします...")
        _run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_pyinstaller() -> None:
    """pyinstaller でアプリをビルドする。"""
    _run(["pyinstaller", "installer/app.spec", "--noconfirm"], cwd=ROOT)


def package_mac() -> None:
    """macOS: create-dmg で .dmg を生成する。"""
    if shutil.which("create-dmg") is None:
        print("[ERROR] create-dmg が見つかりません。以下でインストールしてください:")
        print("  brew install create-dmg")
        sys.exit(1)
    _run(["bash", "installer/build_mac.sh"], cwd=ROOT)
    dmg = DIST / "CunningApp.dmg"
    if dmg.exists():
        print(f"\n[SUCCESS] {dmg}")
    else:
        print("[ERROR] .dmg の生成に失敗しました")
        sys.exit(1)


def package_windows() -> None:
    """Windows: Inno Setup で インストーラー .exe を生成する。"""
    # Inno Setup のデフォルトインストールパスを探索する
    iscc_candidates = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        shutil.which("ISCC"),
    ]
    iscc = next((p for p in iscc_candidates if p and Path(p).exists()), None)
    if iscc is None:
        print("[ERROR] Inno Setup が見つかりません。以下でインストールしてください:")
        print("  winget install JRSoftware.InnoSetup")
        sys.exit(1)
    _run([str(iscc), "installer/installer.iss"], cwd=ROOT)
    exe = DIST / "CunningApp_Setup.exe"
    if exe.exists():
        print(f"\n[SUCCESS] {exe}")
    else:
        print("[ERROR] インストーラーの生成に失敗しました")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="CunningApp ビルドスクリプト")
    parser.add_argument(
        "--skip-package",
        action="store_true",
        help="PyInstaller ビルドのみ実行し、dmg/exe の生成をスキップする",
    )
    args = parser.parse_args()

    print(f"=== CunningApp ビルド開始 (platform: {sys.platform}) ===\n")

    ensure_pyinstaller()
    build_pyinstaller()

    if args.skip_package:
        print("\n[INFO] --skip-package が指定されたためパッケージ化をスキップします")
        print(f"ビルド成果物: {DIST / 'CunningApp'}")
        return

    if sys.platform == "darwin":
        package_mac()
    elif sys.platform == "win32":
        package_windows()
    else:
        print(f"[WARN] 未対応の platform ({sys.platform})。ビルドのみ完了しました。")
        print(f"ビルド成果物: {DIST / 'CunningApp'}")


if __name__ == "__main__":
    main()
```

---

## 配布物の確認チェックリスト

### macOS

```bash
# ビルド実行
python build.py

# 生成物の確認
ls -lh dist/CunningApp.dmg

# dmg をマウントして App を Applications にドラッグ
open dist/CunningApp.dmg

# Applications から起動してテスト
# ✅ SetupDialog が表示されること（初回）
# ✅ APIキーを入力して保存後、メインウィンドウが表示されること
# ✅ アクセシビリティ権限のダイアログが表示されること（pynput）
# ✅ 画面収録権限のダイアログが表示されること（mss）
# ✅ Cmd+Shift+Space でスクリーンキャプチャ → AI回答が表示されること
```

### Windows

```powershell
# ビルド実行
python build.py

# 生成物の確認
dir dist\CunningApp_Setup.exe

# インストーラーを実行
dist\CunningApp_Setup.exe

# スタートメニュー or デスクトップのショートカットから起動してテスト
# ✅ SetupDialog が表示されること（初回）
# ✅ Ctrl+Shift+Space でスクリーンキャプチャ → AI回答が表示されること
```

---

## `requirements-build.txt` の作成

ビルド専用の依存を本体の `requirements.txt` と分離して管理すること:

```
# requirements-build.txt
pyinstaller>=6.0.0
```

このファイルを新規作成し、README または CLAUDE.md に以下を追記すること:

```bash
# ビルド環境のセットアップ
pip install -r requirements-build.txt
python build.py
```

---

## 完了基準

- [ ] `python build.py --skip-package` が正常終了し `dist/CunningApp/` が生成される
- [ ] macOS: `python build.py` が正常終了し `dist/CunningApp.dmg` が生成される
- [ ] macOS: `.dmg` をマウント → アプリ起動 → SetupDialog → メイン画面の遷移が動作する
- [ ] Windows: `python build.py` が正常終了し `dist/CunningApp_Setup.exe` が生成される
- [ ] `requirements-build.txt` が作成されている
