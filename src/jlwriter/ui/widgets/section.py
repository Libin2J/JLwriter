"""对话框里仍在使用的两个小部件：空状态与提示框。

颜色全部交给 QSS 的 role 规则，避免在夜读主题下出现深色文字压深色底。
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PyQt5.QtCore import Qt
from ...ui.tokens import SPACING


class EmptyState(QWidget):
    """空状态：大图标 + 主文案 + 辅助说明"""

    def __init__(self, icon_text, message, hint="", parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignCenter)
        layout.setSpacing(SPACING.sm)

        i = QLabel(icon_text)
        i.setAlignment(Qt.AlignCenter)
        i.setProperty("role", "empty-glyph")
        layout.addWidget(i)

        m = QLabel(message)
        m.setAlignment(Qt.AlignCenter)
        m.setProperty("role", "subtitle")
        layout.addWidget(m)

        if hint:
            h = QLabel(hint)
            h.setAlignment(Qt.AlignCenter)
            h.setProperty("role", "hint")
            h.setWordWrap(True)
            layout.addWidget(h)


class HintBox(QFrame):
    """带左侧强调条的提示框"""

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setProperty("role", "hint-box")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(SPACING.md, SPACING.sm,
                                  SPACING.md, SPACING.sm)

        label = QLabel(text)
        label.setWordWrap(True)
        label.setProperty("role", "caption")
        layout.addWidget(label)
