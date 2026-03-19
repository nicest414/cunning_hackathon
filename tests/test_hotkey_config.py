"""core/hotkey_config.py のユニットテスト。"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from core import hotkey_config


class TestHotkeyConfig(unittest.TestCase):
    def test_load_creates_default_file_when_missing(self):
        """設定ファイルがない場合、既定値ファイルを生成する。"""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with patch("core.hotkey_config._config_dir", return_value=config_dir):
                overrides = hotkey_config.load_hotkey_overrides()

                self.assertEqual(overrides, {})
                config_path = hotkey_config.get_hotkey_config_path()
                self.assertTrue(config_path.exists())

                payload = json.loads(config_path.read_text(encoding="utf-8"))
                self.assertEqual(payload.get("hotkeys", {}), hotkey_config.DEFAULT_HOTKEYS)

    def test_load_reads_only_known_string_values(self):
        """未知キーや不正型を無視して既知キーのみ読み込む。"""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with patch("core.hotkey_config._config_dir", return_value=config_dir):
                config_path = hotkey_config.get_hotkey_config_path()
                config_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "version": 1,
                    "hotkeys": {
                        "panic": "mod+shift+z",
                        "unknown": "alt+9",
                        "quit": 123,
                    },
                }
                config_path.write_text(json.dumps(payload), encoding="utf-8")

                overrides = hotkey_config.load_hotkey_overrides()
                self.assertEqual(overrides, {"panic": "mod+shift+z"})

    def test_load_reads_only_known_bool_flags(self):
        """フラグは既知キーかつ bool 型のみ読み込む。"""
        with tempfile.TemporaryDirectory() as tmp:
            config_dir = Path(tmp)
            with patch("core.hotkey_config._config_dir", return_value=config_dir):
                config_path = hotkey_config.get_hotkey_config_path()
                config_path.parent.mkdir(parents=True, exist_ok=True)
                payload = {
                    "version": 1,
                    "hotkeys": {},
                    "flags": {
                        "audio_vote_enabled": False,
                        "unknown": True,
                        "audio_vote_enabled_str": "false",
                    },
                }
                config_path.write_text(json.dumps(payload), encoding="utf-8")

                flag_overrides = hotkey_config.load_flag_overrides()
                self.assertEqual(flag_overrides, {"audio_vote_enabled": False})

    def test_resolve_hotkeys_merges_with_defaults(self):
        """上書き値を既定値へマージした結果を返す。"""
        resolved = hotkey_config.resolve_hotkeys({"panic": "mod+shift+z"})

        self.assertEqual(resolved["panic"], "mod+shift+z")
        self.assertEqual(resolved["ai_answer"], hotkey_config.DEFAULT_HOTKEYS["ai_answer"])

    def test_resolve_flags_merges_with_defaults(self):
        """フラグ上書き値を既定フラグへマージした結果を返す。"""
        resolved = hotkey_config.resolve_flags({"audio_vote_enabled": False})

        self.assertEqual(resolved["audio_vote_enabled"], False)


if __name__ == "__main__":
    unittest.main()
