"""メニューバートレイアイコン — 投票結果・AI回答をアイコンの色と数字で表示。

画面上に大きなオーバーレイを出さず、macOS メニューバーの小さなアイコンだけで
カンニング情報を伝達するステルス UI。
"""
from __future__ import annotations

from collections import Counter

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

# 選択肢ごとの配色（1=赤, 2=青, 3=緑, 4=橙）
_ANSWER_COLORS: dict[int, QColor] = {
    1: QColor(220, 50, 50),
    2: QColor(50, 120, 220),
    3: QColor(50, 180, 50),
    4: QColor(230, 150, 0),
}
_NEUTRAL_COLOR = QColor(110, 110, 110)

_ICON_SIZE = 22  # macOS メニューバーの標準サイズ


def _make_icon(color: QColor, label: str = "") -> QIcon:
    """指定色の塗りつぶし円 + 中央ラベルでアイコンを生成する。"""
    px = QPixmap(_ICON_SIZE, _ICON_SIZE)
    px.fill(Qt.GlobalColor.transparent)

    p = QPainter(px)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    # 塗りつぶし円
    p.setBrush(color)
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(1, 1, _ICON_SIZE - 2, _ICON_SIZE - 2)

    # ラベル
    if label:
        p.setPen(QColor(255, 255, 255))
        font = QFont("Arial", 11, QFont.Weight.Bold)
        p.setFont(font)
        p.drawText(px.rect(), Qt.AlignmentFlag.AlignCenter, label)

    p.end()
    return QIcon(px)


class TrayIcon(QSystemTrayIcon):
    """メニューバーに常駐してステルスで回答・投票状況を示すトレイアイコン。

    - AI 回答受信時: 対応色の円 + 数字に変化（5 秒後にリセット）
    - 投票更新時: 最多票の選択肢色に変化 / ツールチップで詳細確認可
    - 待機時: グレーの中立アイコン
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setIcon(_make_icon(_NEUTRAL_COLOR))
        self.setToolTip("待機中")
        self.show()

        # 右クリックメニュー（最低限）
        menu = QMenu()
        quit_action = menu.addAction("終了")
        quit_action.triggered.connect(QApplication.instance().quit)
        self.setContextMenu(menu)

        # 一定時間後に中立状態へ戻すタイマー
        self._reset_timer = QTimer()
        self._reset_timer.setSingleShot(True)
        self._reset_timer.timeout.connect(self._reset)

    # ------------------------------------------------------------------
    # 公開 API
    # ------------------------------------------------------------------

    def show_answer(self, answer: str) -> None:
        """AI 回答（1〜4 or ?）をアイコンに反映する。"""
        if answer in ("1", "2", "3", "4"):
            n = int(answer)
            color = _ANSWER_COLORS[n]
        else:
            color = _NEUTRAL_COLOR

        self.setIcon(_make_icon(color, answer))
        self.setToolTip(f"AI: {answer}")
        self._reset_timer.start(5000)

    def show_votes(self, votes: Counter) -> None:
        """投票集計をアイコンに反映する。最多票の選択肢色 + 数字で表示。"""
        if not votes:
            return

        top, _ = votes.most_common(1)[0]
        color = _ANSWER_COLORS.get(top, _NEUTRAL_COLOR)
        self.setIcon(_make_icon(color, str(top)))

        # ツールチップは近くで見ないと読めないので詳細を置く
        summary = "  ".join(
            f"{'▶' if k == top else ' '}{k}:{votes[k]}" for k in sorted(votes)
        )
        self.setToolTip(summary)
        self._reset_timer.start(5000)

    def show_question(self, question_no: int) -> None:
        """現在の問題番号をアイコンとツールチップに表示する（3秒後にリセット）。"""
        self.setIcon(_make_icon(_NEUTRAL_COLOR, f"Q{question_no}"))
        self.setToolTip(f"Q{question_no}")
        self._reset_timer.start(3000)

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        self.setIcon(_make_icon(_NEUTRAL_COLOR))
        self.setToolTip("待機中")
