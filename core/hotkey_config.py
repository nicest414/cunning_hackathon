"""ホットキー設定の永続化ユーティリティ。"""
from __future__ import annotations

import json
import os
import platform
from pathlib import Path
from typing import Final

# キーアクションごとの既定値。mod は macOS で cmd、他OSで ctrl を表す。
DEFAULT_HOTKEYS: Final[dict[str, str]] = {
    "ai_answer": "mod+shift+space",
    "copy_hijack": "mod+shift+c",
    "panic": "mod+shift+a",
    "quit": "mod+shift+x",
    "vote_1": "alt+1",
    "vote_2": "alt+2",
    "vote_3": "alt+3",
    "vote_4": "alt+4",
    "question_up": "alt+up",
    "question_down": "alt+down",
}

DEFAULT_FLAGS: Final[dict[str, bool]] = {
    "audio_vote_enabled": True,
}


def _config_dir() -> Path:
    """OSごとの設定保存先ディレクトリを返す。"""
    sys_name = platform.system()
    if sys_name == "Windows":
        base = Path(os.environ.get("APPDATA", str(Path.home())))
        return base / "InputMonitor"
    if sys_name == "Darwin":
        return Path.home() / "Library" / "Application Support" / "InputMonitor"
    return Path.home() / ".config" / "input_monitor"


def get_hotkey_config_path() -> Path:
    """ホットキー設定ファイルパスを返す。"""
    return _config_dir() / "hotkeys.json"


def _write_default_file(path: Path) -> None:
    """既定値の設定ファイルを作成する。"""
    payload = {
        "version": 1,
        "hotkeys": DEFAULT_HOTKEYS,
        "flags": DEFAULT_FLAGS,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_hotkey_overrides() -> dict[str, str]:
    """設定ファイルからホットキー上書き値を読み込む。失敗時は空辞書を返す。"""
    path = get_hotkey_config_path()

    try:
        if not path.exists():
            _write_default_file(path)
            return {}

        raw = json.loads(path.read_text(encoding="utf-8"))
        hotkeys = raw.get("hotkeys", {}) if isinstance(raw, dict) else {}
        if not isinstance(hotkeys, dict):
            return {}

        merged: dict[str, str] = {}
        for action in DEFAULT_HOTKEYS:
            value = hotkeys.get(action)
            if isinstance(value, str):
                merged[action] = value
        return merged
    except Exception:
        # 設定破損時もアプリを止めない
        return {}


def resolve_hotkeys(overrides: dict[str, str] | None = None) -> dict[str, str]:
    """既定値に上書き値を反映した辞書を返す。"""
    resolved = dict(DEFAULT_HOTKEYS)
    for action, combo in (overrides or {}).items():
        if action in resolved and isinstance(combo, str):
            resolved[action] = combo
    return resolved


def load_flag_overrides() -> dict[str, bool]:
    """設定ファイルから機能フラグ上書き値を読み込む。失敗時は空辞書を返す。"""
    path = get_hotkey_config_path()

    try:
        if not path.exists():
            _write_default_file(path)
            return {}

        raw = json.loads(path.read_text(encoding="utf-8"))
        flags = raw.get("flags", {}) if isinstance(raw, dict) else {}
        if not isinstance(flags, dict):
            return {}

        merged: dict[str, bool] = {}
        for key in DEFAULT_FLAGS:
            value = flags.get(key)
            if isinstance(value, bool):
                merged[key] = value
        return merged
    except Exception:
        # 設定破損時もアプリを止めない
        return {}


def resolve_flags(overrides: dict[str, bool] | None = None) -> dict[str, bool]:
    """既定フラグに上書き値を反映した辞書を返す。"""
    resolved = dict(DEFAULT_FLAGS)
    for key, value in (overrides or {}).items():
        if key in resolved and isinstance(value, bool):
            resolved[key] = value
    return resolved


def humanize_hotkey(combo: str) -> str:
    """表示用のホットキー表記に変換する。"""
    token_map = {
        "mod": "Cmd" if platform.system() == "Darwin" else "Ctrl",
        "shift": "Shift",
        "alt": "Option" if platform.system() == "Darwin" else "Alt",
        "space": "Space",
        "up": "↑",
        "down": "↓",
    }
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    return "+".join(token_map.get(part, part.upper() if len(part) == 1 else part) for part in parts)
