# Step 3 — `main.py` のライフサイクル分岐リファクタリング

## このステップでやること

`main.py` を改修し、以下の起動フローを実現する。

```
python main.py 起動
  │
  ▼
APIキーの取得優先順位:
  1. keyring (credentials.get_api_key())
  2. 環境変数 GEMINI_API_KEY（.env 含む、後方互換のため残す）
  │
  ├─ キーが取得できた → MainWindow を直接起動
  │
  └─ キーが取得できない → SetupDialog を表示
        │
        ├─ accept (保存して起動) → MainWindow を起動
        └─ reject (キャンセル)   → アプリ終了 (sys.exit(0))
```

**前提: Step 1・Step 2 が完了していること。**

---

## 変更対象ファイル

- `main.py` のみ

---

## 変更内容の詳細

### import の追加

以下を追加する:

```python
from core import credentials
from ui.setup_dialog import SetupDialog
```

`from dotenv import load_dotenv` は引き続き残す（後方互換）。

---

### `main()` 関数の冒頭部分の変更

#### 変更前（現在の実装）

```python
def main() -> None:
    load_dotenv()

    api_key = os.getenv("GEMINI_API_KEY", "")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY が設定されていません。.env を確認してください。")
        sys.exit(1)

    ai_client.init(api_key)
    # ... 以降の処理
```

#### 変更後

```python
def main() -> None:
    load_dotenv()  # .env を環境変数に反映（後方互換）

    # APIキー取得: keyring → 環境変数 の優先順位
    api_key = credentials.get_api_key() or os.getenv("GEMINI_API_KEY", "")

    # QApplication は SetupDialog を表示する前に生成する必要がある
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    if not api_key:
        dialog = SetupDialog()
        result = dialog.exec()
        if result != SetupDialog.DialogCode.Accepted:
            sys.exit(0)
        # SetupDialog.accept() 内で credentials.set_api_key() が呼ばれているので
        # ここで再取得する
        api_key = credentials.get_api_key() or ""
        if not api_key:
            # 万が一取得できなかった場合（通常は起こらない）
            sys.exit(1)

    ai_client.init(api_key)

    # --- 以降は既存の処理をそのまま維持 ---
    _notifier = create_notifier()
    # ※ QApplication の生成を main() 冒頭に移動したため、
    #    既存の `app = QApplication(sys.argv)` の行を削除すること

    overlay = OverlayWindow()
    # ... 残りの既存コードは一切変更しない
```

---

## 注意事項

### `QApplication` の生成タイミング

現在の `main.py` では `ai_client.init(api_key)` の後に `app = QApplication(sys.argv)` を生成している。
`SetupDialog` は `QDialog` なので `QApplication` が先に存在している必要がある。

**対処:** `app = QApplication(sys.argv)` の行を `main()` 冒頭（APIキー取得処理より前）に移動する。
それ以外の既存コードの順序は変更しない。

### `print` による起動ログ

既存の起動完了メッセージ（`print("カンニングアプリ 起動完了。")` 等）はそのまま維持すること。

### `.env` ファイルの後方互換

- `load_dotenv()` の呼び出しは残す
- `os.getenv("GEMINI_API_KEY", "")` のフォールバックも残す
- これにより既存の開発環境（`.env` を使っている環境）では動作が変わらない

---

## 実装後の確認

### テスト 1: keyring にキーなし・環境変数なしの場合

```bash
source .venv/bin/activate
# .env の GEMINI_API_KEY を空にするか、一時的にリネームして実行
python main.py
# → SetupDialog が表示されること
# → キャンセルするとアプリが終了すること
```

### テスト 2: keyring にキーありの場合

```bash
# Step 1 で実装した credentials モジュールを使って手動でキーを保存
python -c "from core.credentials import set_api_key; set_api_key('your-actual-api-key')"
python main.py
# → SetupDialog が表示されず、直接起動すること
```

### テスト 3: 既存テストが壊れていないことの確認

```bash
python -m pytest tests/ -v
```

全テストが green であること。

---

## 完了基準

- [ ] `main.py` が `QApplication` 生成前に `SetupDialog` を呼ばないよう修正されている
- [ ] keyring にキーがある場合は SetupDialog をスキップして起動する
- [ ] keyring にキーがない場合は SetupDialog が表示される
- [ ] キャンセル時はアプリが終了する
- [ ] `.env` の `GEMINI_API_KEY` によるフォールバックが引き続き動作する
- [ ] `python -m pytest tests/ -v` が全て green
