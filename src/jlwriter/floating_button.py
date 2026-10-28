"""
助手悬浮窗
"""
import os
from PyQt5.QtWidgets import QWidget, QPushButton, QMenu, QAction
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QSize
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QPen

from .paths import get_icon_file
# 图标文件路径（与主脚本同目录下的 ai_icon.ico）
ICON_FILE = str(get_icon_file())

class FloatingAssistantButton(QWidget):
    toggle_requested = pyqtSignal(bool)
    settings_requested = pyqtSignal()
    outline_requested = pyqtSignal()
    chat_requested = pyqtSignal()  # 新增对话请求
    characters_extract_requested = pyqtSignal()  # 新增角色拉取
    characters_view_requested = pyqtSignal()  # 新增角色关系提取
    planner_requested = pyqtSignal()        #新增AI策划
    deviation_requested = pyqtSignal()
    prompt_viewer_requested = pyqtSignal()  # 新增prompt历史记录

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stay_on_top = False  # 新增
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(40, 40)

        self.btn = QPushButton(self)
        self.btn.setFixedSize(40, 40)
        self._load_icon()
        self.btn.setIconSize(QSize(25, 25))
        self.btn.setStyleSheet("""
            QPushButton {
                background-color: rgba(0, 0, 0, 255);
                border-radius: 20px;
                border: none;
            }
            QPushButton:hover {
                background-color: rgba(30, 30, 30, 240);
            }
        """)
        self.btn.clicked.connect(self.show_menu)

        self._parent = parent
        self._dragging = False
        self._offset = QPoint()

    def _load_icon(self):
        if os.path.exists(ICON_FILE):
            self.btn.setIcon(QIcon(ICON_FILE))
        else:
            self.btn.setIcon(self._create_default_icon())
        self.btn.setText("")

    def _create_default_icon(self):
        """内置 AI 图标（备用）"""
        pixmap = QPixmap(30, 30)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)

        # 外圈圆环（黑色背景已提供，这里用白色线条）
        pen = QPen(QColor(255, 255, 255), 2)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(2, 2, 26, 26)

        pen.setWidth(2)
        painter.setPen(pen)
        points_left = [QPoint(10, 18), QPoint(10, 10), QPoint(14, 14), QPoint(10, 18)]
        painter.drawPolyline(*points_left)
        points_right = [QPoint(20, 18), QPoint(20, 10), QPoint(16, 14), QPoint(20, 18)]
        painter.drawPolyline(*points_right)

        painter.end()
        return QIcon(pixmap)

    def show_menu(self):
        menu = QMenu(self)
        menu.addAction("AI 对话", self.chat_requested.emit)
        menu.addAction("AI 策划（从零构建）", self.planner_requested.emit)
        menu.addAction("对比当前章节规划", self.deviation_requested.emit)
        menu.addSeparator()
        menu.addAction("提取故事档案", self.characters_extract_requested.emit)
        menu.addAction("查看故事档案", self.characters_view_requested.emit)
        menu.addSeparator()
        menu.addAction("立即整理大纲", self.outline_requested.emit)
        menu.addSeparator()

        menu.addAction("查看最近 Prompt", self.prompt_viewer_requested.emit)
        stay_action = QAction("始终置顶显示", self, checkable=True)
        stay_action.setChecked(self.stay_on_top)
        stay_action.toggled.connect(self.set_stay_on_top)
        menu.addAction(stay_action)

        menu.addSeparator()
        toggle_action = QAction(
            "暂停助手" if self.parent().ai_config.assistant_enabled else "启用助手", self
        )
        toggle_action.triggered.connect(
            lambda: self.toggle_requested.emit(not self.parent().ai_config.assistant_enabled)
        )
        menu.addAction(toggle_action)
        menu.addAction("助手设置", self.settings_requested.emit)
        menu.exec_(self.mapToGlobal(QPoint(40, 0)))

    def move_to_tree_corner(self):
        if self._parent and self._parent.tree:
            tree = self._parent.tree
            # 获取树的可见区域左上角相对于父窗口的位置
            tree_pos = tree.mapTo(self._parent, QPoint(0, 0))
            tree_width = tree.viewport().width() if tree.viewport() else tree.width()
            # 按钮放在右上角，留出 5px 边距
            x = tree_pos.x() + tree_width - self.width() - 5
            y = tree_pos.y() + 5
            self.move(self._parent.mapToGlobal(QPoint(x, y)))

    def update_position(self):
        self.move_to_tree_corner()

    def _apply_window_flags(self):
        flags = Qt.Tool | Qt.FramelessWindowHint
        if self.stay_on_top:
            flags |= Qt.WindowStaysOnTopHint
        self.setWindowFlags(flags)

    def set_stay_on_top(self, on):
        if self.stay_on_top == on:
            return
        self.stay_on_top = on
        was_visible = self.isVisible()
        self._apply_window_flags()
        if was_visible:
            self.show()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._offset = event.globalPos() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPos() - self._offset)

    def mouseReleaseEvent(self, event):
        self._dragging = False