"""キーバインド設定ダイアログ。"""
import platform
from typing import Optional

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMessageBox, QPushButton, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QHeaderView,
)

from utils import keyconfig

_IS_MAC = platform.system() == "Darwin"

# pynput のキー名 → 表示名
_KEY_DISPLAY: dict[str, str] = {
    "mod":       "Cmd" if _IS_MAC else "Ctrl",
    "shift":     "Shift",
    "alt":       "Option" if _IS_MAC else "Alt",
    "space":     "Space",
    "enter":     "Enter",
    "tab":       "Tab",
    "backspace": "Backspace",
    "delete":    "Delete",
    "esc":       "Escape",
    "up":        "↑",
    "down":      "↓",
    "left":      "←",
    "right":     "→",
}

# Qt の modifier フラグ → 内部キー名
_QT_MOD_MAP = {
    Qt.KeyboardModifier.ControlModifier: "mod",  # Ctrl / Cmd
    Qt.KeyboardModifier.ShiftModifier:   "shift",
    Qt.KeyboardModifier.AltModifier:     "alt",
    Qt.KeyboardModifier.MetaModifier:    "mod",  # macOS では Ctrl が Meta 扱いになる場合がある
}

# Qt のキーコード → 内部キー名
_QT_KEY_MAP: dict[int, str] = {
    Qt.Key.Key_Space.value:     "space",
    Qt.Key.Key_Return.value:    "enter",
    Qt.Key.Key_Enter.value:     "enter",
    Qt.Key.Key_Tab.value:       "tab",
    Qt.Key.Key_Backspace.value: "backspace",
    Qt.Key.Key_Delete.value:    "delete",
    Qt.Key.Key_Escape.value:    "esc",
    Qt.Key.Key_Up.value:        "up",
    Qt.Key.Key_Down.value:      "down",
    Qt.Key.Key_Left.value:      "left",
    Qt.Key.Key_Right.value:     "right",
}


def _keys_to_display(keys: list[str]) -> str:
    return "+".join(_KEY_DISPLAY.get(k, k.upper()) for k in keys)


class _CaptureButton(QPushButton):
    """クリックするとキー入力をキャプチャし、内部表現に変換するボタン。"""

    def __init__(self, keys: list[str], row: int, parent: "KeyConfigDialog") -> None:
        label = _keys_to_display(keys)
        super().__init__(label)
        self._keys = list(keys)
        self._row = row
        self._dialog = parent
        self._capturing = False
        self.clicked.connect(self._start_capture)

    def current_keys(self) -> list[str]:
        return list(self._keys)

    def set_keys(self, keys: list[str]) -> None:
        self._keys = list(keys)
        self.setText(_keys_to_display(keys))

    def _start_capture(self) -> None:
        if self._dialog.capturing_button and self._dialog.capturing_button is not self:
            self._dialog.capturing_button._cancel_capture()
        self._capturing = True
        self._dialog.capturing_button = self
        self.setText("キーを押してください...")
        self.setFocus()

    def _cancel_capture(self) -> None:
        self._capturing = False
        if self._dialog.capturing_button is self:
            self._dialog.capturing_button = None
        self.setText(_keys_to_display(self._keys))

    def keyPressEvent(self, event) -> None:  # type: ignore[override]
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key_int = event.key()
        mods = event.modifiers()

        # 修飾キー単体は無視
        modifier_keys = {
            Qt.Key.Key_Control.value, Qt.Key.Key_Shift.value,
            Qt.Key.Key_Alt.value, Qt.Key.Key_Meta.value,
        }
        if key_int in modifier_keys:
            return

        # Escape でキャンセル
        if key_int == Qt.Key.Key_Escape.value:
            self._cancel_capture()
            return

        parts: list[str] = []

        # macOS では Cmd = Meta, Ctrl = Control
        if _IS_MAC:
            if mods & Qt.KeyboardModifier.MetaModifier:
                parts.append("mod")
            if mods & Qt.KeyboardModifier.ControlModifier:
                parts.append("mod")  # Ctrl も mod 扱い（重複は後でユニーク化）
        else:
            if mods & Qt.KeyboardModifier.ControlModifier:
                parts.append("mod")

        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")

        # ユニーク化（順序維持）
        seen: set[str] = set()
        unique_parts: list[str] = []
        for p in parts:
            if p not in seen:
                seen.add(p)
                unique_parts.append(p)
        parts = unique_parts

        # 修飾キーなしは禁止
        if not parts:
            QMessageBox.warning(self._dialog, "無効な入力", "修飾キー（Cmd/Ctrl、Shift、Alt）と組み合わせてください。")
            return

        # 通常キーを解決
        key_name: Optional[str] = _QT_KEY_MAP.get(key_int)
        if key_name is None:
            char = event.text().lower()
            if char and char.isprintable() and not char.isspace():
                key_name = char
        if key_name is None:
            return

        new_keys = parts + [key_name]

        # 重複チェック
        conflict = self._dialog.find_conflict(self._row, new_keys)
        if conflict:
            QMessageBox.warning(
                self._dialog, "競合",
                f"そのキーは「{conflict}」に割り当て済みです。\n別のキーを選んでください。"
            )
            return

        self._keys = new_keys
        self._capturing = False
        self._dialog.capturing_button = None
        self.setText(_keys_to_display(new_keys))
        event.accept()


class KeyConfigDialog(QDialog):
    """キーバインドを一覧表示し、各アクションのキーを変更できるダイアログ。"""

    def __init__(self, config: dict[str, list[str]], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("キーバインド設定")
        self.setModal(True)
        self.setMinimumWidth(520)

        self.capturing_button: Optional[_CaptureButton] = None
        self._actions = list(keyconfig.ACTION_LABELS.keys())
        self._capture_buttons: list[_CaptureButton] = []

        desc = QLabel("各アクションの「変更」ボタンを押してから、割り当てたいキーを入力してください。")
        desc.setWordWrap(True)

        # テーブル
        self._table = QTableWidget(len(self._actions), 2)
        self._table.setHorizontalHeaderLabels(["アクション", "キーバインド"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._table.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        for row, action in enumerate(self._actions):
            label_item = QTableWidgetItem(keyconfig.ACTION_LABELS[action])
            self._table.setItem(row, 0, label_item)

            btn = _CaptureButton(config[action], row, self)
            self._capture_buttons.append(btn)
            self._table.setCellWidget(row, 1, btn)

        # ボタン行
        reset_btn = QPushButton("デフォルトに戻す")
        reset_btn.clicked.connect(self._on_reset)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_box.button(QDialogButtonBox.StandardButton.Ok).setText("保存して起動")
        btn_box.button(QDialogButtonBox.StandardButton.Cancel).setText("キャンセル（デフォルトで起動）")
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)

        bottom_row = QHBoxLayout()
        bottom_row.addWidget(reset_btn)
        bottom_row.addStretch()
        bottom_row.addWidget(btn_box)

        layout = QVBoxLayout()
        layout.addWidget(desc)
        layout.addWidget(self._table)
        layout.addLayout(bottom_row)
        self.setLayout(layout)

    def find_conflict(self, exclude_row: int, keys: list[str]) -> Optional[str]:
        """exclude_row 以外の行で同じキーが使われていれば、そのアクション名を返す。"""
        for row, btn in enumerate(self._capture_buttons):
            if row == exclude_row:
                continue
            if btn.current_keys() == keys:
                return keyconfig.ACTION_LABELS[self._actions[row]]
        return None

    def result_config(self) -> dict[str, list[str]]:
        return {
            action: self._capture_buttons[i].current_keys()
            for i, action in enumerate(self._actions)
        }

    def _on_reset(self) -> None:
        defaults = keyconfig.defaults()
        for i, action in enumerate(self._actions):
            self._capture_buttons[i].set_keys(defaults[action])

    def _on_accept(self) -> None:
        config = self.result_config()
        try:
            keyconfig.save(config)
        except Exception as e:
            QMessageBox.critical(self, "保存エラー", f"設定の保存に失敗しました。\n{e}")
            return
        self.accept()
