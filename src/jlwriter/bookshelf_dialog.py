"""
书架对话框：网格展示所有书籍
"""
import os
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QScrollArea, QWidget, QGridLayout, QMessageBox, QMenu, QFileDialog, QDialog
from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ui.widgets.section import EmptyState
from PyQt5.QtCore import Qt

from . import book_manager as bm
from .book_card import BookCard
from .book_meta_dialog import BookMetaDialog


class BookshelfDialog(BaseDialog):
    def __init__(self, parent=None, allow_select=True):
        self.selected_book_dir = None
        self._allow_select = allow_select

        super().__init__(
            parent,
            title="书架",
            subtitle="左键打开；右键设置封面和简介",
            default_size=(1200, 850),
            min_size=(720, 540),
            show_button_bar=False,
        )

        self._refresh()

    def build_content(self, layout):
        # 顶部工具栏
        top = QHBoxLayout()
        top.setSpacing(SPACING.sm)
        top.addStretch()

        self.new_btn = QPushButton("+ 新建书籍")
        self.new_btn.setProperty("role", "primary")
        self.new_btn.clicked.connect(self._on_new)
        top.addWidget(self.new_btn)

        self.import_btn = QPushButton("导入项目...")
        self.import_btn.clicked.connect(self._on_import)
        top.addWidget(self.import_btn)

        layout.addLayout(top)

        # 滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        self.container = QWidget()
        self.grid = QGridLayout(self.container)
        self.grid.setSpacing(20)
        self.grid.setContentsMargins(
            SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm
        )
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.container)
        layout.addWidget(self.scroll, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bar.addWidget(close_btn)
        root_layout.addLayout(bar)

    def _refresh(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        books = bm.list_books()
        if not books:
            empty = EmptyState(
                "📚",
                "书架空空如也",
                "点击右上角「新建书籍」开始创作"
            )
            self.grid.addWidget(empty, 0, 0, 1, 4)
            return

        cols = 4
        for i, book in enumerate(books):
            card = BookCard(book)
            card.clicked.connect(self._on_book_clicked)
            card.right_clicked.connect(self._on_book_right_clicked)
            self.grid.addWidget(card, i // cols, i % cols)

    def _on_book_clicked(self, book_dir):
        if not self._allow_select:
            return
        self.selected_book_dir = book_dir
        self.accept()

    def _on_book_right_clicked(self, book_dir, global_pos):
        menu = QMenu(self)
        menu.addAction("打开", lambda: self._open_book(book_dir))
        menu.addSeparator()
        menu.addAction("编辑信息...", lambda: self._edit_meta(book_dir))
        menu.addAction("更换封面...", lambda: self._change_cover(book_dir))
        menu.addSeparator()
        menu.addAction("删除书籍...", lambda: self._delete_book(book_dir))
        menu.exec_(global_pos)

    def _open_book(self, book_dir):
        if not self._allow_select:
            return
        self.selected_book_dir = book_dir
        self.accept()

    def _edit_meta(self, book_dir):
        dlg = BookMetaDialog(book_dir, self)
        if dlg.exec_() == QDialog.Accepted:
            self._refresh()

    def _change_cover(self, book_dir):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "",
            "图片文件 (*.png *.jpg *.jpeg)"
        )
        if not path:
            return
        if bm.set_cover(book_dir, path):
            self._refresh()
        else:
            QMessageBox.warning(self, "失败", "封面设置失败。")

    def _delete_book(self, book_dir):
        title = os.path.basename(book_dir)
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除《{title}》吗？\n"
            "该操作会删除整个书籍文件夹（含项目、历史记录、封面），"
            "不可撤销。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if bm.delete_book(book_dir):
            self._refresh()
        else:
            QMessageBox.warning(self, "失败", "删除失败。")

    def _on_new(self):
        # 直接弹出书籍信息对话框；保存时自动创建目录
        dlg = BookMetaDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return

        book_dir = dlg.get_book_dir()
        if book_dir:
            self._refresh()
            if self._allow_select:
                self.selected_book_dir = book_dir
                self.accept()

    def _on_import(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择要导入的项目文件", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        book_dir, _ = bm.import_external_project(path)
        if not book_dir:
            QMessageBox.warning(self, "失败", "导入失败。")
            return
        QMessageBox.information(
            self, "导入成功",
            f"已导入到书架：{os.path.basename(book_dir)}"
        )
        self._refresh()

    def get_selected_book_dir(self):
        return self.selected_book_dir