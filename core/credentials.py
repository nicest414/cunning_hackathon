import keyring
import keyring.errors

_SERVICE = "cunning_hackathon"
_USERNAME = "gemini_api_key"


def get_api_key() -> str | None:
    try:
        return keyring.get_password(_SERVICE, _USERNAME)
    except Exception:
        return None


def set_api_key(key: str) -> None:
    keyring.set_password(_SERVICE, _USERNAME, key)


def delete_api_key() -> None:
    try:
        keyring.delete_password(_SERVICE, _USERNAME)
    except keyring.errors.PasswordDeleteError:
        pass
