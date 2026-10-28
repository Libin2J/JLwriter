"""
智能章节大纲（摘要）提取
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPlainTextEdit, QSplitter, QLabel, QMessageBox, QSizePolicy
)
from PyQt5.QtCore import Qt, pyqtSignal
from .models import StoryProject


class OutlineEditor(QWidget):
    """结构化大纲编辑器：左侧树形目录，右侧为选中章节的摘要编辑框"""
    outlineChanged = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project = None
        self.current_chapter = None
        self.current_volume = None
        self._building = False
        self._suppress_signals = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题（高度受控，不抢占空间）
        self.title_label = QLabel("故事大纲")
        self.title_label.setStyleSheet("font-weight: bold; padding: 4px; background: transparent;")
        self.title_label.setMaximumHeight(25)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self.title_label)

        # 水平分割器：左侧章节列表，右侧摘要编辑
        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)  # stretch factor 1，占据剩余全部空间

        # 左侧树
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(5)
        self.tree.setMinimumWidth(80)
        # 关键改动：响应键盘方向键
        self.tree.currentItemChanged.connect(self._on_current_item_changed)
        splitter.addWidget(self.tree)

        # 右侧摘要编辑区域
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(4, 4, 4, 4)

        self.chapter_label = QLabel("选择章节编辑摘要")
        self.chapter_label.setMaximumHeight(20)
        right_layout.addWidget(self.chapter_label)

        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setPlaceholderText("在此编写该章节的摘要...")
        self.summary_edit.setMinimumWidth(100)
        self.summary_edit.textChanged.connect(self.on_summary_changed)
        right_layout.addWidget(self.summary_edit)

        splitter.addWidget(right_widget)
        splitter.setChildrenCollapsible(True)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

    def load_project(self, project: StoryProject):
        self.project = project
        self.refresh_tree()
        self.summary_edit.clear()
        self.current_chapter = None
        self.current_volume = None

    def refresh_tree(self):
        self._suppress_signals = True
        self._building = True
        self.tree.clear()
        for vi, vol in enumerate(self.project.volumes):
            vol_item = QTreeWidgetItem(self.tree, [vol.title])
            vol_item.setData(0, Qt.UserRole, ("volume", vi))
            for ci, ch in enumerate(vol.chapters):
                ch_item = QTreeWidgetItem(vol_item, [ch.title])
                ch_item.setData(0, Qt.UserRole, ("chapter", vi, ci))
            vol_item.setExpanded(True)
        self._building = False
        self._suppress_signals = False

    def _on_current_item_changed(self, current, previous):
        if self._building or self._suppress_signals or current is None:
            return
        self._on_item_selected(current)

    def _on_item_selected(self, item):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] == "chapter":
            vi, ci = data[1], data[2]
            if vi >= len(self.project.volumes):
                return
            vol = self.project.volumes[vi]
            if ci >= len(vol.chapters):
                return
            ch = vol.chapters[ci]
            self.current_volume = vol
            self.current_chapter = ch
            self.chapter_label.setText(f"《{vol.title}》- {ch.title}")
            self.summary_edit.blockSignals(True)
            self.summary_edit.setPlainText(ch.summary)
            self.summary_edit.blockSignals(False)
            self.summary_edit.setReadOnly(False)
        else:
            self.current_chapter = None
            self.current_volume = None
            self.chapter_label.setText("选择章节编辑摘要")
            self.summary_edit.clear()
            self.summary_edit.setReadOnly(True)

    def on_summary_changed(self):
        if self.current_chapter is not None:
            self.current_chapter.summary = self.summary_edit.toPlainText()
            self.outlineChanged.emit()

    def auto_generate_empty_summaries(self):
        if not self.project:
            return
        updated = False
        for vol in self.project.volumes:
            for ch in vol.chapters:
                if not ch.summary.strip():
                    content = ch.content.strip()
                    if content:
                        summary = content[:100].replace('\n', ' ')
                        if len(content) > 100:
                            summary += "..."
                        ch.summary = summary
                        updated = True
                    else:
                        ch.summary = "（无内容）"
                        updated = True
        if updated:
            self.refresh_current_summary()
            self.refresh_tree()
            QMessageBox.information(self, "自动大纲", "已为空白章节生成摘要。")
        else:
            QMessageBox.information(self, "自动大纲", "所有章节均已包含摘要，无需生成。")

    def refresh_current_summary(self):
        if self.current_chapter:
            self.summary_edit.blockSignals(True)
            self.summary_edit.setPlainText(self.current_chapter.summary)
            self.summary_edit.blockSignals(False)

    def update_chapter_summary(self, vol_title: str, ch_title: str, summary: str):
        """更新指定章节的摘要，仅刷新相关控件，避免完全重建"""
        if not self.project:
            return

        # 更新对应树节点（可选，树节点只显示标题，无需改动）
        # 如果当前编辑框恰好显示该章节，则更新编辑框内容
        if self.current_chapter and self.current_volume:
            if self.current_volume.title == vol_title and self.current_chapter.title == ch_title:
                self.summary_edit.blockSignals(True)
                self.summary_edit.setPlainText(summary)
                self.summary_edit.blockSignals(False)

    def set_editor_font(self, font):
        self.summary_edit.setFont(font)

    def sync_to_model(self):
        """编辑即保存，无需手动同步"""
        pass