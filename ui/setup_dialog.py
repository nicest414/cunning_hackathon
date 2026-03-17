import threading

from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import (
    QDialog, QLabel, QLineEdit, QPushButton,
    QHBoxLayout, QVBoxLayout, QMessageBox,
)
from google import genai

from core import credentials


def _validate_api_key(key: str) -> bool:
    try:
        client = genai.Client(api_key=key)
        next(iter(client.models.list()))
        return True
    except Exception:
        return False


class _Validator(QObject):
    finished = pyqtSignal(bool)

    def __init__(self, key: str):
        super().__init__()
        self._key = key

    def run(self) -> None:
        ok = _validate_api_key(self._key)
        self.finished.emit(ok)


class SetupDialog(QDialog):
    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Gemini API キーの設定")
        self.setModal(True)
        self.setFixedWidth(420)

        description = QLabel(
            "Gemini API キーを入力してください。\n"
            "入力されたキーは OS のセキュアストレージに保存されます。"
        )
        description.setWordWrap(True)

        self._key_edit = QLineEdit()
        self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)

        self._toggle_btn = QPushButton("表示")
        self._toggle_btn.setFixedWidth(60)
        self._toggle_btn.clicked.connect(self._on_toggle_visibility)

        key_row = QHBoxLayout()
        key_row.addWidget(QLabel("API キー:"))
        key_row.addWidget(self._key_edit)
        key_row.addWidget(self._toggle_btn)

        self._cancel_btn = QPushButton("キャンセル")
        self._save_btn = QPushButton("保存して起動")
        self._cancel_btn.clicked.connect(self._on_cancel)
        self._save_btn.clicked.connect(self._on_save)

        btn_row = QHBoxLayout()
        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._save_btn)

        layout = QVBoxLayout()
        layout.addWidget(description)
        layout.addLayout(key_row)
        layout.addLayout(btn_row)
        self.setLayout(layout)

        self._pending_key: str = ""

    def _on_toggle_visibility(self) -> None:
        if self._key_edit.echoMode() == QLineEdit.EchoMode.Password:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Normal)
            self._toggle_btn.setText("隠す")
        else:
            self._key_edit.setEchoMode(QLineEdit.EchoMode.Password)
            self._toggle_btn.setText("表示")

    def _on_save(self) -> None:
        key = self._key_edit.text().strip()
        if not key:
            QMessageBox.warning(self, "入力エラー", "API キーを入力してください。")
            return

        self._pending_key = key
        self._save_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._save_btn.setText("確認中...")

        validator = _Validator(key)
        validator.finished.connect(self._on_validate_done)
        threading.Thread(target=validator.run, daemon=True).start()
        self._validator = validator  # keep reference

    def _on_validate_done(self, ok: bool) -> None:
        self._save_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        self._save_btn.setText("保存して起動")

        if ok:
            try:
                credentials.set_api_key(self._pending_key)
            except Exception as e:
                self._pending_key = ""
                QMessageBox.critical(
                    self,
                    "保存エラー",
                    f"API キーの保存に失敗しました。\n{e}",
                )
                return
            self.accept()
        else:
            QMessageBox.critical(
                self,
                "認証エラー",
                "API キーが無効か、接続に失敗しました。\nキーを確認してもう一度お試しください。",
            )

    def _on_cancel(self) -> None:
        self.reject()
