"""
全文搜索对话框：搜索结果以“书目条目”的方式呈现，双击跳转。
"""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QLabel, QTreeWidget, QTreeWidgetItem

from .ui.literary import FramedDialog


class BookSearchDialog(FramedDialog):
    """搜索对话框：可搜索整本书或单个章节，双击跳转到匹配位置。"""

    jump_to = pyqtSignal(int, int, str, int)  # vol_idx, ch_idx, term, position

    def __init__(self, project, term, parent=None, chapter=None, volume=None):
        self.project = project
        self.term = term
        super().__init__(
            parent,
            title=f"搜索 · {term}",
            subtitle="正在检索全书……",
            seal_text="寻",
            motto="字里行间，寻一处回响",
        )
        self.resize(900, 650)
        self.setMinimumSize(560, 420)

        self.info_label = QLabel(f"关键词：{term}")
        self.info_label.setProperty("role", "caption")
        self.add_body(self.info_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["位置", "上下文"])
        self.tree.setRootIsDecorated(False)
        self.tree.setAlternatingRowColors(True)
        self.tree.setColumnWidth(0, 300)
        self.tree.header().setStretchLastSection(True)
        self.tree.doubleClicked.connect(self.on_double_click)
        self.add_body(self.tree, 1)

        self.empty_label = QLabel("没有找到匹配的段落，换个词试试。")
        self.empty_label.setProperty("role", "hint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.hide()
        self.add_body(self.empty_label)

        self.add_button("关闭", self.close, variant="quiet", default=True)

        self.populate(chapter, volume)

        count = self.tree.topLevelItemCount()
        if count:
            self.set_subtitle(f"“{term}” · 共 {count} 处")
        else:
            self.set_subtitle(f"“{term}” · 没有找到")
            self.tree.hide()
            self.empty_label.show()

    def populate(self, chapter=None, volume=None):
        self.tree.clear()
        if chapter and volume is not None:
            vi = self.project.volumes.index(volume)
            ci = volume.chapters.index(chapter)
            self._populate_chapter(vi, ci, chapter)
        else:
            for vi, vol in enumerate(self.project.volumes):
                for ci, ch in enumerate(vol.chapters):
                    self._populate_chapter(vi, ci, ch)

    def _populate_chapter(self, vi, ci, ch):
        content = ch.content
        idx = 0
        while True:
            idx = content.find(self.term, idx)
            if idx == -1:
                break
            start = max(0, idx - 30)
            end = min(len(content), idx + len(self.term) + 30)
            context = content[start:end].replace("\n", " ")
            item = QTreeWidgetItem(self.tree)
            item.setText(
                0,
                f"第{vi + 1}卷 {self.project.volumes[vi].title} · "
                f"第{ci + 1}章 {ch.title}",
            )
            item.setText(1, f"…{context}…")
            item.setData(0, Qt.UserRole, (vi, ci, idx))
            idx += len(self.term)

    def on_double_click(self, index):
        item = self.tree.currentItem()
        if item:
            vi, ci, pos = item.data(0, Qt.UserRole)
            self.jump_to.emit(vi, ci, self.term, pos)
            self.accept()
