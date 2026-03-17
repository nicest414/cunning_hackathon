# Step 1 — `core/credentials.py` の実装とテスト

## このステップでやること

`keyring` ライブラリを使って Gemini APIキーを OS のセキュアストレージ
（macOS: Keychain、Windows: Credential Manager）に保存・取得・削除する
薄いラッパーモジュール `core/credentials.py` を新規作成する。

あわせてそのユニットテスト `tests/test_credentials.py` も作成する。

**コードはまだ書かないこと。まずこのドキュメントを読んで全体を把握すること。**
準備ができたら以下の仕様に従って実装してほしい。

---

## 前提

- Python 3.10+、PyQt6 環境（既存の `.venv` を使用）
- `keyring` ライブラリを `requirements.txt` に追記し、インストールすること
  ```
  keyring>=25.0.0
  ```
- 既存コードへの変更はこのステップでは行わない

---

## `core/credentials.py` の仕様

### 定数

```python
_SERVICE = "cunning_hackathon"
_USERNAME = "gemini_api_key"
```

### 公開関数（3つのみ）

#### `get_api_key() -> str | None`

- `keyring.get_password(_SERVICE, _USERNAME)` を呼ぶ
- 取得できた場合はその文字列を返す
- 取得できない場合（未保存 or keyring エラー）は `None` を返す
- keyring が利用できない環境（CI など）では例外を握りつぶして `None` を返す

#### `set_api_key(key: str) -> None`

- `keyring.set_password(_SERVICE, _USERNAME, key)` を呼ぶ
- keyring エラー時は例外をそのまま raise する（呼び出し元でハンドリングさせる）

#### `delete_api_key() -> None`

- `keyring.delete_password(_SERVICE, _USERNAME)` を呼ぶ
- キーが存在しない場合（`keyring.errors.PasswordDeleteError`）は無視する
- その他の例外はそのまま raise する

---

## `tests/test_credentials.py` の仕様

`keyring` をモックして、実際の OS キーストアを操作しないようにすること。
`unittest.mock.patch` を使う。

### テストケース

1. **`test_get_returns_none_when_not_set`**
   - `keyring.get_password` が `None` を返すとき、`get_api_key()` が `None` を返すこと

2. **`test_get_returns_key_when_set`**
   - `keyring.get_password` が `"test-key-abc"` を返すとき、`get_api_key()` が `"test-key-abc"` を返すこと

3. **`test_get_returns_none_on_keyring_error`**
   - `keyring.get_password` が `Exception` を raise するとき、`get_api_key()` が `None` を返すこと（例外を握りつぶす）

4. **`test_set_calls_keyring`**
   - `set_api_key("my-key")` を呼ぶと `keyring.set_password(_SERVICE, _USERNAME, "my-key")` が呼ばれること

5. **`test_delete_ignores_not_found`**
   - `keyring.delete_password` が `keyring.errors.PasswordDeleteError` を raise するとき、`delete_api_key()` が例外を raise しないこと

6. **`test_delete_calls_keyring`**
   - `delete_api_key()` を呼ぶと `keyring.delete_password(_SERVICE, _USERNAME)` が呼ばれること

---

## 実装後の確認

以下を実行してすべて green になることを確認すること:

```bash
source .venv/bin/activate
pip install keyring
python -m pytest tests/test_credentials.py -v
```

完了したら次のステップ `step2_setup_dialog.md` に進むこと。
