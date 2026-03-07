"""
sorry.png を生成するヘルパースクリプト。
好みの画像を assets/sorry.png に置けばこのスクリプトは不要です。
実行: python assets/generate_sorry.py
"""
import os
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont, QImage, QPainter, QColor
from PyQt6.QtWidgets import QApplication
import sys

def generate() -> None:
    app = QApplication.instance() or QApplication(sys.argv)

    img = QImage(800, 600, QImage.Format.Format_ARGB32)
    img.fill(QColor("white"))

    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    font = QFont("Arial", 120, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor("#333333"))
    painter.drawText(img.rect(), Qt.AlignmentFlag.AlignCenter, "ごめんなさい")
    painter.end()

    out = os.path.join(os.path.dirname(__file__), "sorry.png")
    img.save(out)
    print(f"生成完了: {out}")

if __name__ == "__main__":
    generate()
