"""OS自動判定ビルドスクリプト。"""
import argparse
import os
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
    dmg = DIST / "InputMonitor.dmg"
    if dmg.exists():
        print(f"\n[SUCCESS] {dmg}")
    else:
        print("[ERROR] .dmg の生成に失敗しました")
        sys.exit(1)


def package_windows() -> None:
    """Windows: Inno Setup で インストーラー .exe を生成する。"""
    # PATH 上の shims / WinGet links / 代表的なインストール先を順に探索する
    iscc_candidates: list[Path] = []
    which_result = shutil.which("ISCC")
    if which_result:
        iscc_candidates.append(Path(which_result))

    program_files = os.environ.get("ProgramFiles")
    program_files_x86 = os.environ.get("ProgramFiles(x86)")
    local_app_data = os.environ.get("LOCALAPPDATA")

    for base in (program_files_x86, program_files):
        if base:
            iscc_candidates.extend(
                [
                    Path(base) / "Inno Setup 6" / "ISCC.exe",
                    Path(base) / "Inno Setup" / "ISCC.exe",
                ]
            )

    if local_app_data:
        iscc_candidates.extend(
            [
                Path(local_app_data) / "Programs" / "Inno Setup 6" / "ISCC.exe",
                Path(local_app_data) / "Programs" / "Inno Setup" / "ISCC.exe",
                Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ISCC.exe",
            ]
        )

        winget_packages_dir = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
        for package_dir in winget_packages_dir.glob("JRSoftware.InnoSetup*"):
            iscc_candidates.append(package_dir / "ISCC.exe")
            iscc_candidates.append(package_dir / "Inno Setup 6" / "ISCC.exe")

    iscc = next((candidate for candidate in iscc_candidates if candidate.exists()), None)
    if iscc is None:
        print("[ERROR] Inno Setup が見つかりません。以下でインストールしてください:")
        print("  winget install JRSoftware.InnoSetup")
        print("[INFO] 探索したパス:")
        for candidate in iscc_candidates:
            print(f"  - {candidate}")
        sys.exit(1)
    _run([str(iscc), "installer/installer.iss"], cwd=ROOT)
    exe = DIST / "InputMonitor_Setup.exe"
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
        print(f"ビルド成果物: {DIST / 'InputMonitor'}")
        return

    if sys.platform == "darwin":
        package_mac()
    elif sys.platform == "win32":
        package_windows()
    else:
        print(f"[WARN] 未対応の platform ({sys.platform})。ビルドのみ完了しました。")
        print(f"ビルド成果物: {DIST / 'InputMonitor'}")


if __name__ == "__main__":
    main()
