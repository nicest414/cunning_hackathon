"""回答表示用の透明クリックスルーオーバーレイ。"""
from collections import Counter

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication, QLabel, QWidget


class OverlayWindow(QWidget):
    """画面右下にひっそりと回答を表示する透明ウィンドウ。"""

    def __init__(self) -> None:
        super().__init__()
        self._setup_window()
        self._setup_label()

    def _setup_window(self) -> None:
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.WindowTransparentForInput,
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        screen = QApplication.primaryScreen().geometry()
        self.setGeometry(screen.width() - 200, screen.height() - 120, 180, 100)

    def _setup_label(self) -> None:
        self._label = QLabel("", self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        font = QFont("Arial", 48, QFont.Weight.Bold)
        self._label.setFont(font)
        self._label.setStyleSheet(
            "color: rgba(255, 60, 60, 200);"
            "background-color: rgba(0, 0, 0, 120);"
            "border-radius: 12px;"
            "padding: 4px 12px;"
        )
        self._label.setGeometry(10, 10, 160, 80)

    def show_answer(self, answer: str) -> None:
        """AI 回答 (1〜4 or ?) を表示する。"""
        self._label.setText(answer)
        self.show()

    def show_votes(self, votes: Counter) -> None:
        """多数決集計結果を表示する。票数最多の選択肢を強調。"""
        if not votes:
            return
        top = votes.most_common(1)[0][0]
        summary = "  ".join(
            f"{'▶' if k == top else ' '}{k}:{votes[k]}" for k in sorted(votes)
        )
        self._label.setFont(QFont("Arial", 14, QFont.Weight.Bold))
        self._label.setText(summary)
        self.show()

    def hide_all(self) -> None:
        self._label.setText("")
        self.hide()
