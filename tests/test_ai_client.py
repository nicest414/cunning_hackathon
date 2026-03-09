"""Unit tests for core/ai_client.py — google.genai は完全にモック化。"""
import importlib
import sys
import types
import unittest
from unittest.mock import MagicMock, patch


def _build_genai_stub():
    """google.genai の最小スタブモジュールを組み立てる。"""
    google_mod = types.ModuleType("google")
    genai_mod = types.ModuleType("google.genai")
    types_mod = types.ModuleType("google.genai.types")

    # types.Part.from_bytes スタブ
    part_stub = MagicMock()
    types_mod.Part = part_stub

    genai_mod.Client = MagicMock()
    genai_mod.types = types_mod
    google_mod.genai = genai_mod

    return google_mod, genai_mod, types_mod


class TestAiClient(unittest.TestCase):
    def setUp(self):
        # google / google.genai をモックに差し替えてからモジュールをインポート
        self.google_mod, self.genai_mod, self.types_mod = _build_genai_stub()

        sys.modules.pop("core.ai_client", None)
        sys.modules["google"] = self.google_mod
        sys.modules["google.genai"] = self.genai_mod
        sys.modules["google.genai.types"] = self.types_mod

        import core.ai_client as ai_client
        self.ai_client = ai_client

        # グローバル _client を毎テストでリセット
        self.ai_client._client = None

    def tearDown(self):
        sys.modules.pop("core.ai_client", None)
        sys.modules.pop("google", None)
        sys.modules.pop("google.genai", None)
        sys.modules.pop("google.genai.types", None)

    # ------------------------------------------------------------------
    def test_init_creates_client(self):
        """init() が genai.Client を api_key 付きで生成する。"""
        self.ai_client.init("test-key-123")
        self.genai_mod.Client.assert_called_once_with(api_key="test-key-123")
        self.assertIsNotNone(self.ai_client._client)

    def test_ask_returns_valid_answer(self):
        """モデルが '1'〜'4' を返すとき、そのまま返す。"""
        mock_client = MagicMock()
        self.ai_client._client = mock_client

        for choice in ("1", "2", "3", "4"):
            mock_response = MagicMock()
            mock_response.text = f"  {choice}  "  # 前後空白あり
            mock_client.models.generate_content.return_value = mock_response

            result = self.ai_client.ask(b"fake-png")
            self.assertEqual(result, choice)

    def test_ask_returns_question_mark_for_unexpected_response(self):
        """モデルが想定外の文字列を返すとき '?' に丸める。"""
        mock_client = MagicMock()
        self.ai_client._client = mock_client

        # "A" は有効な回答扱いなので、"E" や "X" などを代わりにテストする
        for bad_answer in ("5", "E", "X", "", "正解は2番です", "0"):
            mock_response = MagicMock()
            mock_response.text = bad_answer
            mock_client.models.generate_content.return_value = mock_response

            result = self.ai_client.ask(b"fake-png")
            self.assertEqual(result, "?", f"expected '?' for answer={bad_answer!r}")

    # ついでに柔軟なマッピングのテストを追加するとより完璧です
    def test_ask_maps_letters_to_numbers(self):
        """A, B, ア, イなどを 1, 2, 3, 4 にマッピングする"""
        mock_client = MagicMock()
        self.ai_client._client = mock_client

        cases = {"A": "1", "B": "2", "ア": "1", "ウ": "3"}
        for letter, expected_number in cases.items():
            mock_response = MagicMock()
            mock_response.text = letter
            mock_client.models.generate_content.return_value = mock_response

            result = self.ai_client.ask(b"fake-png")
            self.assertEqual(result, expected_number)

    def test_ask_passes_correct_model_name(self):
        """generate_content が正しいモデル名で呼ばれる。"""
        mock_client = MagicMock()
        self.ai_client._client = mock_client
        mock_response = MagicMock()
        mock_response.text = "2"
        mock_client.models.generate_content.return_value = mock_response

        self.ai_client.ask(b"fake-png")

        call_kwargs = mock_client.models.generate_content.call_args
        self.assertIn("gemini", call_kwargs.kwargs.get("model", call_kwargs.args[0] if call_kwargs.args else ""))

    def test_ask_passes_image_bytes(self):
        """ask() に渡した PNG バイト列が contents に含まれる。"""
        mock_client = MagicMock()
        self.ai_client._client = mock_client
        mock_response = MagicMock()
        mock_response.text = "3"
        mock_client.models.generate_content.return_value = mock_response

        image_bytes = b"\x89PNG\r\nfake"
        self.ai_client.ask(image_bytes)

        # types.Part.from_bytes が image_bytes を引数に呼ばれているか
        self.types_mod.Part.from_bytes.assert_called_once_with(
            data=image_bytes, mime_type="image/png"
        )

    def test_ask_without_init_raises(self):
        """init() を呼ばずに ask() するとエラーになる。"""
        self.ai_client._client = None
        with self.assertRaises(AssertionError):
            self.ai_client.ask(b"fake-png")


if __name__ == "__main__":
    unittest.main()
