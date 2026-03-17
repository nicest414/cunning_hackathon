"""緊急謝罪全画面ウィンドウ。先生が近づいてきたときに使う。"""
import os

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
_SORRY_IMAGE = os.path.join(_ASSETS_DIR, "gomen.png")
_AUTO_CLOSE_MS = 5000  # 5秒後に自動で消える


class ApologyWindow(QWidget):
    """全画面で「ごめんなさい」を表示し、5秒後に自動で閉じる。"""

    def __init__(self) -> None:
        super().__init__()
        self._setup_window()
        self._setup_content()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen)
        self.setStyleSheet("background-color: white;")

    def _setup_content(self) -> None:
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pixmap = QPixmap(_SORRY_IMAGE)
        if pixmap.isNull():
            # sorry.png が無い場合はテキストでフォールバック
            self._label.setStyleSheet("font-size: 120px; font-weight: bold; color: #333;")
            self._label.setText("ごめんなさい")
        else:
            screen = QApplication.primaryScreen().geometry()
            self._label.setPixmap(
                pixmap.scaled(
                    screen.width(),
                    screen.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

        self._label.setGeometry(self.rect())

    def apologize(self) -> None:
        """謝罪を開始する。5秒後に自動で消える。"""
        self._label.setGeometry(self.rect())
        self.show()
        self.raise_()
        self.activateWindow()
        self._timer.start(_AUTO_CLOSE_MS)
