"""
Prompt 查看器：展示最近发送给 LLM 的 prompt，供审查与优化
"""
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QPlainTextEdit, QComboBox,
    QMessageBox, QFileDialog, QSplitter, QWidget, QApplication,
    QAbstractItemView
)
from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont

from .prompt_history import PromptHistory


class PromptViewerDialog(BaseDialog):
    def __init__(self, parent=None):
        self.history = PromptHistory.instance()
        self._filtered_records = []

        super().__init__(
            parent,
            title="Prompt 查看器",
            subtitle="查看最近发送给 LLM 的完整 prompt（含 system 与 user）",
            default_size=(1200, 850),
            min_size=(820, 540),
            show_button_bar=False,
        )

        self.history.updated.connect(self._on_history_updated)
        self._refresh()

    def build_content(self, layout):
        # 顶部工具条
        top = QHBoxLayout()
        top.setSpacing(SPACING.sm)
        top.addWidget(QLabel("筛选 Agent:"))

        self.filter_combo = QComboBox()
        self.filter_combo.addItem("全部")
        self.filter_combo.setMinimumWidth(160)
        self.filter_combo.currentIndexChanged.connect(
            self._on_filter_changed
        )
        top.addWidget(self.filter_combo)

        self.count_label = QLabel("0 条记录")
        self.count_label.setProperty("role", "hint")
        top.addWidget(self.count_label)

        top.addStretch()

        refresh_btn = QPushButton("刷新")
        refresh_btn.setProperty("role", "ghost")
        refresh_btn.clicked.connect(self._refresh)
        top.addWidget(refresh_btn)

        clear_btn = QPushButton("清空历史")
        clear_btn.setProperty("role", "danger")
        clear_btn.clicked.connect(self._on_clear)
        top.addWidget(clear_btn)

        layout.addLayout(top)

        # 主体：左列表 + 右详情
        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("最近记录（新→旧）："))

        self.list_widget = QListWidget()
        self.list_widget.currentRowChanged.connect(self._on_record_selected)
        self.list_widget.setWordWrap(True)
        self.list_widget.setSelectionMode(
            QAbstractItemView.SingleSelection
        )
        left_layout.addWidget(self.list_widget)
        left.setMinimumWidth(300)

        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.info_label = QLabel("请选择左侧一条记录")
        self.info_label.setProperty("role", "hint")
        self.info_label.setWordWrap(True)
        right_layout.addWidget(self.info_label)

        self.detail_edit = QPlainTextEdit()
        self.detail_edit.setReadOnly(True)
        mono = QFont("Consolas", 10)
        mono.setStyleHint(QFont.Monospace)
        self.detail_edit.setFont(mono)
        right_layout.addWidget(self.detail_edit, 1)

        btn_row = QHBoxLayout()
        btn_row.addStretch()

        copy_btn = QPushButton("复制 Prompt")
        copy_btn.clicked.connect(self._on_copy)
        btn_row.addWidget(copy_btn)

        save_btn = QPushButton("保存为文件...")
        save_btn.clicked.connect(self._on_save_file)
        btn_row.addWidget(save_btn)

        right_layout.addLayout(btn_row)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setProperty("role", "primary")
        close_btn.clicked.connect(self.accept)
        bar.addWidget(close_btn)
        root_layout.addLayout(bar)

    # ============================================================
    # 刷新与筛选
    # ============================================================
    def _refresh(self):
        # 更新筛选下拉框
        current = self.filter_combo.currentText()
        names = self.history.agent_names()

        self.filter_combo.blockSignals(True)
        self.filter_combo.clear()
        self.filter_combo.addItem("全部")
        for n in names:
            self.filter_combo.addItem(n)
        idx = self.filter_combo.findText(current)
        if idx >= 0:
            self.filter_combo.setCurrentIndex(idx)
        self.filter_combo.blockSignals(False)

        self._rebuild_list()

    def _on_history_updated(self):
        # 有新记录时刷新
        self._refresh()

    def _on_filter_changed(self):
        self._rebuild_list()

    def _rebuild_list(self):
        selected_agent = self.filter_combo.currentText()
        records = self.history.all_records()

        if selected_agent and selected_agent != "全部":
            records = [r for r in records if r.agent_name == selected_agent]

        self._filtered_records = records

        # 记住当前选中项的时间戳
        cur_row = self.list_widget.currentRow()
        cur_ts = None
        if 0 <= cur_row < len(self._filtered_records):
            cur_ts = self._filtered_records[cur_row].timestamp

        self.list_widget.blockSignals(True)
        self.list_widget.clear()

        for r in self._filtered_records:
            text = (
                f"[{r.short_time}] {r.agent_name}\n"
                f"{r.summary(48)}"
            )
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, r.timestamp)
            self.list_widget.addItem(item)

        self.list_widget.blockSignals(False)

        self.count_label.setText(f"{len(records)} 条记录")

        # 恢复选中
        if self._filtered_records:
            target_row = 0
            if cur_ts is not None:
                for i, r in enumerate(self._filtered_records):
                    if r.timestamp == cur_ts:
                        target_row = i
                        break
            self.list_widget.setCurrentRow(target_row)
            self._on_record_selected(target_row)
        else:
            self.info_label.setText("暂无记录")
            self.detail_edit.clear()
            self.list_widget.clear()
            item = QListWidgetItem("（暂无记录）")
            item.setFlags(Qt.NoItemFlags)
            self.list_widget.addItem(item)

    # ============================================================
    # 详情
    # ============================================================
    def _on_record_selected(self, row):
        if row < 0 or row >= len(self._filtered_records):
            self.info_label.setText("请选择左侧一条记录")
            self.detail_edit.clear()
            return

        r = self._filtered_records[row]
        self.info_label.setText(
            f"时间：{r.time_str}　｜　"
            f"Agent：{r.agent_name}　｜　"
            f"模型：{r.model or '（未指定）'}　｜　"
            f"长度：{len(r.prompt)} 字"
        )
        self.detail_edit.setPlainText(r.prompt)

    # ============================================================
    # 操作
    # ============================================================
    def _get_current_record(self):
        row = self.list_widget.currentRow()
        if row < 0 or row >= len(self._filtered_records):
            return None
        return self._filtered_records[row]

    def _on_copy(self):
        r = self._get_current_record()
        if not r:
            QMessageBox.information(self, "提示", "请先选择一条记录。")
            return
        QApplication.clipboard().setText(r.prompt)
        QMessageBox.information(self, "已复制", "Prompt 已复制到剪贴板。")

    def _on_save_file(self):
        r = self._get_current_record()
        if not r:
            QMessageBox.information(self, "提示", "请先选择一条记录。")
            return
        default_name = (
            f"prompt_{r.agent_name}_"
            f"{r.time_str.replace(':', '-').replace(' ', '_')}.txt"
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "保存 Prompt", default_name,
            "文本文件 (*.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(f"时间: {r.time_str}\n")
                f.write(f"Agent: {r.agent_name}\n")
                f.write(f"模型: {r.model}\n")
                f.write(f"Provider: {r.provider}\n")
                f.write("=" * 60 + "\n\n")
                f.write(r.prompt)
            QMessageBox.information(self, "已保存", f"已保存到：\n{path}")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", str(e))

    def _on_clear(self):
        if not self.history.all_records():
            return
        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空所有 prompt 记录吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self.history.clear()
        self._refresh()

    def closeEvent(self, event):
        try:
            self.history.updated.disconnect(self._on_history_updated)
        except Exception:
            pass
        super().closeEvent(event)