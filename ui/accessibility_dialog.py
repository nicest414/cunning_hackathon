"""アクセシビリティ権限の誘導ダイアログ。"""
import os
import sys

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog, QDialogButtonBox, QLabel, QPushButton, QVBoxLayout,
)

from utils import accessibility


class AccessibilityDialog(QDialog):
    """アクセシビリティ権限が未付与の場合に表示する誘導ダイアログ。

    macOS の TCC 仕様により、権限付与はプロセス再起動後でないと反映されない。
    ユーザが権限をオンにしたら「再起動して適用」でアプリを再起動する。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("アクセシビリティ権限が必要です")
        self.setModal(True)
        self.setMinimumWidth(420)

        self._label = QLabel(
            "キーボードショートカットを使用するには\n"
            "アクセシビリティ権限が必要です。\n\n"
            "① 下のボタンを押してシステム設定を開く\n"
            "② 「プライバシーとセキュリティ」→「アクセシビリティ」で\n"
            "　 このアプリをオンにする\n"
            "③「再起動して適用」を押す"
        )
        self._label.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self._label.setWordWrap(True)

        self._open_btn = QPushButton("システム設定を開く")
        self._open_btn.clicked.connect(self._open_settings)

        btn_box = QDialogButtonBox()
        self._restart_btn = btn_box.addButton("再起動して適用", QDialogButtonBox.ButtonRole.AcceptRole)
        self._quit_btn = btn_box.addButton("終了", QDialogButtonBox.ButtonRole.RejectRole)
        self._restart_btn.clicked.connect(self._restart)
        self._quit_btn.clicked.connect(self.reject)

        layout = QVBoxLayout()
        layout.addWidget(self._label)
        layout.addWidget(self._open_btn)
        layout.addWidget(btn_box)
        self.setLayout(layout)

    def _open_settings(self) -> None:
        import subprocess
        # macOS バージョンによって有効な URL が異なるため順番に試す
        # Ventura(13)以降は "System Settings"、それ以前は "System Preferences"
        urls = [
            "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension?Privacy_Accessibility",
            "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility",
        ]
        for url in urls:
            result = subprocess.run(["open", url], capture_output=True)
            if result.returncode == 0:
                return
        # 上記が全滅した場合はシステム設定のトップを開く
        subprocess.Popen(["open", "-b", "com.apple.systempreferences"])

    def _restart(self) -> None:
        """現プロセスを exec で置き換えて再起動する。"""
        os.execv(sys.executable, [sys.executable] + sys.argv)
