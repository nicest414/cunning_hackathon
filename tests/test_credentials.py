from unittest.mock import patch
import keyring.errors
import pytest

from core.credentials import get_api_key, set_api_key, delete_api_key, _SERVICE, _USERNAME


def test_get_returns_none_when_not_set():
    with patch("keyring.get_password", return_value=None):
        assert get_api_key() is None


def test_get_returns_key_when_set():
    with patch("keyring.get_password", return_value="test-key-abc"):
        assert get_api_key() == "test-key-abc"


def test_get_returns_none_on_keyring_error():
    with patch("keyring.get_password", side_effect=Exception("keyring unavailable")):
        assert get_api_key() is None


def test_set_calls_keyring():
    with patch("keyring.set_password") as mock_set:
        set_api_key("my-key")
        mock_set.assert_called_once_with(_SERVICE, _USERNAME, "my-key")


def test_delete_ignores_not_found():
    with patch("keyring.delete_password", side_effect=keyring.errors.PasswordDeleteError("not found")):
        delete_api_key()  # should not raise


def test_delete_calls_keyring():
    with patch("keyring.delete_password") as mock_del:
        delete_api_key()
        mock_del.assert_called_once_with(_SERVICE, _USERNAME)
