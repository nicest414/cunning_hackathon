"""Gemini API クライアント — 画面画像を送って四択の番号を返す。"""
import base64
from google import genai
from google.genai import types

# Gemini 3.1 Flash Lite Previewを使用する（間違いなく存在してます！）
_MODEL_NAME = "gemini-3.1-flash-lite-preview"

_PROMPT = (
    "この画像はPC画面のスクリーンショットです。"
    "四択問題が表示されている場合、正解の選択肢番号（1・2・3・4のいずれか）だけを返してください。"
    "問題が見当たらない場合や判断できない場合は「?」とだけ返してください。"
    "余計な説明は不要です。"
)

_client: genai.Client | None = None


def init(api_key: str) -> None:
    global _client
    _client = genai.Client(api_key=api_key)


_FALLBACK_MODEL = "gemini-2.5-flash"  # または gemini-1.5-flash 等の安定的・軽量なモデル

def ask(image_bytes: bytes) -> str:
    """PNG バイト列を Gemini Flash に送り、回答番号文字列を返す。"""
    assert _client is not None, "ai_client.init() を先に呼び出してください"
    
    contents = [
        types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        _PROMPT,
    ]
    
    try:
        response = _client.models.generate_content(
            model=_MODEL_NAME,
            contents=contents,
        )
    except Exception as e:
        print(f"[DEBUG] {_MODEL_NAME} でのエラー ({e})。{_FALLBACK_MODEL} で再試行します...")
        try:
            response = _client.models.generate_content(
                model=_FALLBACK_MODEL,
                contents=contents,
            )
        except Exception as e2:
            print(f"[ERROR] フォールバックモデルも失敗しました: {e2}")
            return "?"

    answer = response.text.strip()
    
    # 少し柔軟に解釈（ア,イ,ウ,エ や A,B,C,D を 1,2,3,4 にマッピング）
    mapping = {
        "1": "1", "2": "2", "3": "3", "4": "4",
        "ア": "1", "イ": "2", "ウ": "3", "エ": "4",
        "A": "1", "B": "2", "C": "3", "D": "4",
        "a": "1", "b": "2", "c": "3", "d": "4",
    }
    
    # 安全弁: 想定外が返ってきた場合は ? に丸める
    if answer in mapping:
        return mapping[answer]
    return "?"
