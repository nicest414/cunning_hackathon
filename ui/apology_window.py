"""緊急謝罪全画面ウィンドウ。先生が近づいてきたときに使う。"""
import os
import random

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication, QLabel, QWidget

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "..", "assets")
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
_AUTO_CLOSE_MS = 5000  # 5秒後に自動で消える


def _pick_random_image() -> str | None:
    """assets ディレクトリから画像ファイルをランダムに1枚選ぶ。取得できない場合は None を返す。"""
    try:
        images = [
            os.path.join(_ASSETS_DIR, f)
            for f in os.listdir(_ASSETS_DIR)
            if os.path.splitext(f)[1].lower() in _IMAGE_EXTENSIONS
        ]
        return random.choice(images) if images else None
    except (FileNotFoundError, PermissionError, OSError):
        return None


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
        self._label.setGeometry(self.rect())

    def _load_random_image(self) -> None:
        """ランダムに選んだ画像をラベルにセットする。"""
        image_path = _pick_random_image()
        pixmap = QPixmap(image_path) if image_path else QPixmap()
        if pixmap.isNull():
            self._label.setStyleSheet("font-size: 120px; font-weight: bold; color: #333;")
            self._label.setPixmap(QPixmap())
            self._label.setText("ごめんなさい")
        else:
            self._label.setStyleSheet("")
            self._label.setText("")
            screen = QApplication.primaryScreen().geometry()
            self._label.setPixmap(
                pixmap.scaled(
                    screen.width(),
                    screen.height(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
            )

    def apologize(self) -> None:
        """謝罪を開始する。5秒後に自動で消える。"""
        self._load_random_image()
        self._label.setGeometry(self.rect())
        self.show()
        self.raise_()
        self.activateWindow()
        self._timer.start(_AUTO_CLOSE_MS)
