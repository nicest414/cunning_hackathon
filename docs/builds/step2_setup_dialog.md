# Step 2 — `ui/setup_dialog.py` の実装

## このステップでやること

初回起動時に表示する「Gemini APIキー入力ダイアログ」を PyQt6 の `QDialog` として実装する。

**前提: Step 1（`core/credentials.py`）が完了していること。**

---

## 完成イメージ

```
┌─────────────────────────────────────────────┐
│          Gemini API キーの設定               │
├─────────────────────────────────────────────┤
│                                             │
│  Gemini API キーを入力してください。         │
│  入力されたキーは OS のセキュアストレージ     │
│  に保存されます。                            │
│                                             │
│  API キー: [________________________] [表示] │
│                                             │
│  [キャンセル]                    [保存して起動] │
└─────────────────────────────────────────────┘
```

---

## `ui/setup_dialog.py` の仕様

### クラス: `SetupDialog(QDialog)`

#### `__init__(self, parent=None)`

- ウィンドウタイトル: `"Gemini API キーの設定"`
- モーダルダイアログ（`setModal(True)`）
- 固定サイズ推奨（幅 420px 程度）
- レイアウト構成:
  1. 説明ラベル（複数行）
  2. APIキー入力行: `QLabel("API キー:")` + `QLineEdit` + `QPushButton("表示")`
  3. ボタン行: `QPushButton("キャンセル")` + `QPushButton("保存して起動")`

#### `QLineEdit` の設定

- `setEchoMode(QLineEdit.EchoMode.Password)` でデフォルトはマスク表示
- 「表示」ボタンを押すたびに `Normal` / `Password` をトグルする
- ボタンのテキストも「表示」/「隠す」でトグルする

#### `_on_save()` スロット（「保存して起動」ボタンの clicked に接続）

1. `QLineEdit.text().strip()` でキーを取得
2. 空文字の場合: `QMessageBox.warning` でエラーを表示して処理を中断
3. Gemini API の疎通確認（後述）を行う
4. 成功した場合: `credentials.set_api_key(key)` で保存 → `self.accept()` でダイアログを閉じる
5. 失敗した場合: `QMessageBox.critical` でエラーメッセージを表示

#### `_on_cancel()` スロット（「キャンセル」ボタンの clicked に接続）

- `self.reject()` を呼ぶ

#### Gemini API 疎通確認の実装方針

`ui/setup_dialog.py` 内で直接 `google.genai.Client` を使って疎通確認する。
具体的には以下の処理を行う:

```python
from google import genai

def _validate_api_key(key: str) -> bool:
    """APIキーが有効かどうかを確認する。有効なら True、無効なら False を返す。"""
    try:
        client = genai.Client(api_key=key)
        # モデルリストを取得して疎通確認（軽量な呼び出し）
        list(client.models.list())
        return True
    except Exception:
        return False
```

疎通確認中はボタンを非活性化し（`setEnabled(False)`）、
ボタンテキストを `"確認中..."` に変更すること。
確認完了後は元に戻すこと。

疎通確認は `QThread` または `threading.Thread` で非同期実行し、
**UI スレッドをブロックしないこと**。

非同期実行には以下のパターンを使う:

```python
import threading
from PyQt6.QtCore import QObject, pyqtSignal

class _Validator(QObject):
    finished = pyqtSignal(bool)  # True: 成功, False: 失敗

    def __init__(self, key: str):
        super().__init__()
        self._key = key

    def run(self) -> None:
        ok = _validate_api_key(self._key)
        self.finished.emit(ok)
```

`threading.Thread(target=validator.run, daemon=True).start()` で実行し、
`finished` シグナルを `_on_validate_done(ok: bool)` スロットに接続する。

#### `_on_validate_done(ok: bool)` スロット

- `ok=True`: `credentials.set_api_key(key)` → `self.accept()`
- `ok=False`: エラーダイアログを表示、ボタンを再び活性化

---

## 既存コードとの関係

- `core/credentials.py` を import して使う
- `ui/__init__.py` は変更不要（既存のまま）
- このダイアログは `main.py` から呼ばれる（Step 3 で実装）

---

## 実装後の確認

以下のスクリプトで単体動作確認ができること:

```bash
source .venv/bin/activate
python -c "
from PyQt6.QtWidgets import QApplication
from ui.setup_dialog import SetupDialog
import sys
app = QApplication(sys.argv)
d = SetupDialog()
result = d.exec()
print('result:', result)  # 1=accept, 0=reject
"
```

ダイアログが表示され、キャンセルで 0、保存で 1 が表示されれば OK。
（APIキーの実際の保存は keyring に依存するため、ここでは UI の動作確認のみでよい）

完了したら次のステップ `step3_main_refactor.md` に進むこと。
