"""
章节多选对话框：用于选择需要提取角色画像的章节
"""
from .ui.literary import LiteraryDialog
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QTreeWidget, QTreeWidgetItem, QPushButton, QLabel, QDialogButtonBox
from PyQt5.QtCore import Qt


class ChapterSelectDialog(LiteraryDialog):
    def __init__(self, project, parent=None, title="选择章节"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(480, 560)
        self.project = project

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("勾选需要提取角色画像的章节（可多选）："))

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        layout.addWidget(self.tree)

        # 全选 / 全不选
        btn_row = QHBoxLayout()
        select_all_btn = QPushButton("全选")
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_all_btn = QPushButton("全不选")
        deselect_all_btn.clicked.connect(lambda: self._set_all(False))
        btn_row.addWidget(select_all_btn)
        btn_row.addWidget(deselect_all_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

        self._populate()

    def _populate(self):
        self.tree.clear()
        for vi, vol in enumerate(self.project.volumes):
            vol_item = QTreeWidgetItem(self.tree, [f"第{vi + 1}卷 {vol.title}"])
            vol_item.setFlags(vol_item.flags() | Qt.ItemIsUserCheckable)
            vol_item.setCheckState(0, Qt.Unchecked)
            vol_item.setData(0, Qt.UserRole, ("volume", vi))
            for ci, ch in enumerate(vol.chapters):
                ch_item = QTreeWidgetItem(vol_item, [f"第{ci + 1}章 {ch.title}"])
                ch_item.setFlags(ch_item.flags() | Qt.ItemIsUserCheckable)
                ch_item.setCheckState(0, Qt.Unchecked)
                ch_item.setData(0, Qt.UserRole, ("chapter", vi, ci))
            vol_item.setExpanded(True)

        # 卷勾选联动章节
        self.tree.itemChanged.connect(self._on_item_changed)

    def _on_item_changed(self, item, col):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] == "volume":
            state = item.checkState(0)
            self.tree.blockSignals(True)
            for i in range(item.childCount()):
                item.child(i).setCheckState(0, state)
            self.tree.blockSignals(False)

    def _set_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        self.tree.blockSignals(True)
        for i in range(self.tree.topLevelItemCount()):
            vol_item = self.tree.topLevelItem(i)
            vol_item.setCheckState(0, state)
            for j in range(vol_item.childCount()):
                vol_item.child(j).setCheckState(0, state)
        self.tree.blockSignals(False)

    def get_selected_chapters(self):
        """返回 [(vol_idx, ch_idx), ...]，按卷/章顺序排列"""
        result = []
        for i in range(self.tree.topLevelItemCount()):
            vol_item = self.tree.topLevelItem(i)
            for j in range(vol_item.childCount()):
                ch_item = vol_item.child(j)
                if ch_item.checkState(0) == Qt.Checked:
                    data = ch_item.data(0, Qt.UserRole)
                    if data and data[0] == "chapter":
                        result.append((data[1], data[2]))
        result.sort()
        return result