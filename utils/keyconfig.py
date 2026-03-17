"""キーバインド設定の永続化・ロードモジュール。"""
import json
import os
import platform
from pathlib import Path
from typing import Any

_APP_NAME = "CunningApp"

# アクション名 → デフォルトキーリスト（OS問わず "cmd"/"ctrl" は key_listener 側で解釈）
_DEFAULTS: dict[str, list[str]] = {
    "ai_answer":         ["mod", "shift", "space"],
    "clipboard_replace": ["mod", "shift", "c"],
    "vote_1":            ["alt", "1"],
    "vote_2":            ["alt", "2"],
    "vote_3":            ["alt", "3"],
    "vote_4":            ["alt", "4"],
    "panic":             ["mod", "shift", "a"],
    "quit":              ["mod", "shift", "x"],
}

# UI 表示ラベル
ACTION_LABELS: dict[str, str] = {
    "ai_answer":         "AI回答（スクリーンキャプチャ）",
    "clipboard_replace": "クリップボードAI置換",
    "vote_1":            "多数決 選択肢1",
    "vote_2":            "多数決 選択肢2",
    "vote_3":            "多数決 選択肢3",
    "vote_4":            "多数決 選択肢4",
    "panic":             "緊急謝罪",
    "quit":              "アプリ終了",
}


def _config_dir() -> Path:
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    elif system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home() / ".config"
    return base / _APP_NAME


def _config_path() -> Path:
    return _config_dir() / "keyconfig.json"


def load() -> dict[str, list[str]]:
    """設定ファイルを読み込む。存在しない・不正な場合はデフォルトを返す。"""
    path = _config_path()
    if not path.exists():
        return dict(_DEFAULTS)
    try:
        with open(path, encoding="utf-8") as f:
            data: Any = json.load(f)
        config = dict(_DEFAULTS)
        for key, val in data.items():
            if key in _DEFAULTS and isinstance(val, list) and all(isinstance(k, str) for k in val):
                config[key] = [s.lower() for s in val]
        return config
    except Exception as e:
        print(f"[KeyConfig] 設定ファイルの読み込みに失敗しました（デフォルトを使用）: {e}")
        return dict(_DEFAULTS)


def save(config: dict[str, list[str]]) -> None:
    """設定をファイルに保存する。"""
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def defaults() -> dict[str, list[str]]:
    return dict(_DEFAULTS)


def config_exists() -> bool:
    return _config_path().exists()


def format_keys(keys: list[str]) -> str:
    """キーリストを表示用文字列に変換する。例: ["mod", "shift", "space"] → "Cmd+Shift+Space" """
    is_mac = platform.system() == "Darwin"
    label_map = {
        "mod":   "Cmd" if is_mac else "Ctrl",
        "shift": "Shift",
        "alt":   "Option" if is_mac else "Alt",
        "space": "Space",
    }
    return "+".join(label_map.get(k, k.upper()) for k in keys)
