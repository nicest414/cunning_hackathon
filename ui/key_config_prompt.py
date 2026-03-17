"""起動時のキーバインド変更確認ダイアログ。"""
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QLabel, QVBoxLayout


_TIMEOUT_SEC = 5


class KeyConfigPrompt(QDialog):
    """「キーバインドを変更しますか？」を確認する小さなダイアログ。

    タイムアウト経過でキャンセル（そのまま起動）として自動クローズする。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("キーバインド設定")
        self.setModal(True)
        self.setFixedWidth(360)

        self._remaining = _TIMEOUT_SEC
        self._label = QLabel()
        self._label.setWordWrap(True)
        self._update_label()

        btn_box = QDialogButtonBox()
        self._change_btn = btn_box.addButton("変更する", QDialogButtonBox.ButtonRole.AcceptRole)
        self._skip_btn = btn_box.addButton("このまま起動", QDialogButtonBox.ButtonRole.RejectRole)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self._label)
        layout.addWidget(btn_box)
        self.setLayout(layout)

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(1000)

    def _update_label(self) -> None:
        self._label.setText(
            f"キーバインドを変更しますか？\n\n"
            f"（{self._remaining}秒後に自動的にそのまま起動します）"
        )

    def _tick(self) -> None:
        self._remaining -= 1
        self._update_label()
        if self._remaining <= 0:
            self._timer.stop()
            self.reject()
