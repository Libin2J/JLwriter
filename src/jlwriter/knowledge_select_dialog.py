"""
精修前的知识库选择对话框
"""
from .ui.literary import LiteraryDialog
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox, QGroupBox, QSpinBox, QMessageBox, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt

from . import knowledge_manager as km


class KnowledgeSelectDialog(LiteraryDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("精修参考设置")
        self.resize(760, 760)

        layout = QVBoxLayout(self)

        intro = QLabel(
            "可选择让 AI 精修时参考知识库中的案例。\n"
            "知识库位于程序的 knowledge/ 目录下，可自行扩充。"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        # ============ AI 味去除模板 ============
        ai_group = QGroupBox("AI 味去除模板")
        ai_layout = QVBoxLayout(ai_group)

        self.ai_check = QCheckBox("链接 AI 味去除模板（全部传入）")
        self.ai_check.setChecked(True)
        ai_layout.addWidget(self.ai_check)

        self.ai_hint = QLabel(
            "从 knowledge/ai_style.md 读取全部模板，"
            "帮助 AI 识别并消除典型的 AI 写作痕迹。"
        )
        self.ai_hint.setProperty("role", "hint")
        self.ai_hint.setWordWrap(True)
        ai_layout.addWidget(self.ai_hint)

        if not km.ai_style_exists():
            self.ai_check.setChecked(False)
            self.ai_check.setEnabled(False)
            self.ai_hint.setText(
                "未找到 knowledge/ai_style.md，"
                "请创建该文件后启用此选项。"
            )
            self.ai_hint.setProperty("role", "error")

        layout.addWidget(ai_group)

        # ============ 文笔提升参考 ============
        style_group = QGroupBox("文笔提升参考")
        style_layout = QVBoxLayout(style_group)

        self.style_check = QCheckBox("链接文笔模板")
        self.style_check.setChecked(True)
        self.style_check.toggled.connect(self._on_style_toggled)
        style_layout.addWidget(self.style_check)

        style_layout.addWidget(QLabel("选择参考文件（可多选）:"))

        self.file_list = QListWidget()
        self.file_list.setMaximumHeight(140)
        style_layout.addWidget(self.file_list)

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("每个文件的每节随机抽取:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 50)
        self.count_spin.setValue(10)
        count_row.addWidget(self.count_spin)
        count_row.addWidget(QLabel("条"))
        count_row.addStretch()
        style_layout.addLayout(count_row)

        style_hint = QLabel(
            "「人物描写 / 对话描写 / 环境描写」各节分别随机抽取。"
        )
        style_hint.setProperty("role", "hint")
        style_hint.setWordWrap(True)
        style_layout.addWidget(style_hint)

        layout.addWidget(style_group)

        self._load_files()
        layout.addStretch()

        # ============ 底部按钮 ============
        bottom = QHBoxLayout()
        skip_btn = QPushButton("不使用知识库")
        skip_btn.clicked.connect(self._on_skip)
        bottom.addWidget(skip_btn)
        bottom.addStretch()

        ok_btn = QPushButton("开始精修")
        ok_btn.clicked.connect(self._on_ok)
        bottom.addWidget(ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)

        layout.addLayout(bottom)

        self._on_style_toggled(self.style_check.isChecked())

    def _load_files(self):
        files = km.list_style_files()
        self.file_list.clear()
        if not files:
            self.style_check.setChecked(False)
            self.style_check.setEnabled(False)
            item = QListWidgetItem("（knowledge/ 下无文笔模板文件）")
            item.setFlags(Qt.NoItemFlags)
            self.file_list.addItem(item)
            return

        for i, f in enumerate(files):
            item = QListWidgetItem(f["display"])
            item.setData(Qt.UserRole, f["name"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            # 默认勾选第一个
            item.setCheckState(Qt.Checked if i == 0 else Qt.Unchecked)
            self.file_list.addItem(item)

    def _on_style_toggled(self, checked):
        self.file_list.setEnabled(checked)
        self.count_spin.setEnabled(checked)

    def _get_selected_files(self):
        result = []
        for i in range(self.file_list.count()):
            item = self.file_list.item(i)
            if item.checkState() == Qt.Checked:
                name = item.data(Qt.UserRole)
                if name:
                    result.append(name)
        return result

    def _on_skip(self):
        self.ai_check.setChecked(False)
        self.style_check.setChecked(False)
        self.accept()

    def _on_ok(self):
        if self.style_check.isChecked() and not self._get_selected_files():
            QMessageBox.warning(
                self, "提示",
                "已勾选「链接文笔模板」，但未选择任何文件。"
            )
            return

        if not self.ai_check.isChecked() and not self.style_check.isChecked():
            reply = QMessageBox.question(
                self, "确认",
                "两项都未勾选，精修将不使用任何知识库。是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

        self.accept()

    def get_result(self):
        return {
            "use_ai_style": self.ai_check.isChecked(),
            "use_style": self.style_check.isChecked(),
            "style_files": self._get_selected_files(),
            "sample_count": self.count_spin.value(),
        }