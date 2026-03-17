"""keyring を使った Gemini API キーの永続化ユーティリティ。

取得: keyring から読み込み、エラー時は None を返す。
保存: keyring に書き込む（呼び出し元で例外を処理すること）。
削除: 存在しない場合は無視する。
"""
import keyring
import keyring.errors

_SERVICE = "cunning_hackathon"
_USERNAME = "gemini_api_key"


def get_api_key() -> str | None:
    """keyring から API キーを取得する。取得できない場合は None を返す。"""
    try:
        return keyring.get_password(_SERVICE, _USERNAME)
    except Exception:
        return None


def set_api_key(key: str) -> None:
    """API キーを keyring に保存する。失敗時は例外を送出する。"""
    keyring.set_password(_SERVICE, _USERNAME, key)


def delete_api_key() -> None:
    """keyring から API キーを削除する。存在しない場合は何もしない。"""
    try:
        keyring.delete_password(_SERVICE, _USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass
