"""
书籍卡片：封面 + 书名；左键打开，右键弹菜单

配色全部来自文学风主题：默认封面会随主题重建，夜读/护眼/书卷下都不刺眼。
"""
import os

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QFrame, QLabel, QVBoxLayout

from .ui.literary import current_palette, kai_family, repolish
from .ui.literary.controller import controller


CARD_WIDTH = 150
CARD_HEIGHT = 220


class BookCard(QFrame):
    clicked = pyqtSignal(str)
    right_clicked = pyqtSignal(str, object)

    def __init__(self, book_info, parent=None):
        super().__init__(parent)
        self.book_info = book_info
        self.book_dir = book_info["dir"]
        self.setProperty("role", "book-card")
        self.setProperty("hover", "false")
        self.setFixedSize(CARD_WIDTH + 20, CARD_HEIGHT + 56)
        self.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(6)

        self.cover_label = QLabel()
        self.cover_label.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.cover_label.setAlignment(Qt.AlignCenter)
        self._load_cover()
        layout.addWidget(self.cover_label)

        self.title_label = QLabel(book_info.get("title") or "未命名")
        self.title_label.setAlignment(Qt.AlignCenter)
        self.title_label.setWordWrap(True)
        self.title_label.setMaximumHeight(36)
        self.title_label.setProperty("role", "caption")
        layout.addWidget(self.title_label)

        controller().theme_changed.connect(self._on_theme_changed)

    def _on_theme_changed(self, _key: str) -> None:
        self._load_cover()
        repolish(self)

    def _load_cover(self):
        cover_path = self.book_info.get("cover")
        if cover_path and os.path.exists(cover_path):
            pix = QPixmap(cover_path)
            if not pix.isNull():
                scaled = pix.scaled(
                    CARD_WIDTH,
                    CARD_HEIGHT,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                self.cover_label.setPixmap(scaled)
                return
        self.cover_label.setPixmap(self._draw_default_cover())

    def _draw_default_cover(self):
        palette = current_palette()
        pix = QPixmap(CARD_WIDTH, CARD_HEIGHT)
        pix.fill(QColor(palette.surface_alt))
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.Antialiasing)

        painter.setPen(QPen(QColor(palette.line_strong), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(7, 7, CARD_WIDTH - 14, CARD_HEIGHT - 14)

        title = self.book_info.get("title") or "未命名"
        display = title[:4]
        painter.setPen(QColor(palette.ink))
        font = QFont(kai_family())
        font.setPointSize(18)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(pix.rect(), Qt.AlignCenter, display)

        painter.setPen(QPen(QColor(palette.accent), 1))
        painter.drawLine(26, CARD_HEIGHT - 30, CARD_WIDTH - 26, CARD_HEIGHT - 30)
        painter.end()
        return pix

    def _apply_style(self, hover: bool) -> None:
        self.setProperty("hover", "true" if hover else "false")
        repolish(self)

    def enterEvent(self, event):
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.book_dir)
        elif event.button() == Qt.RightButton:
            self.right_clicked.emit(self.book_dir, event.globalPos())
        super().mousePressEvent(event)
