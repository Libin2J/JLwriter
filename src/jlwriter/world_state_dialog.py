"""
世界状态生成对话框：展示 AI 生成结果，用户确认后写入
"""
from .ui.literary import LiteraryDialog
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QPlainTextEdit, QMessageBox, QSplitter, QWidget, QProgressBar
from PyQt5.QtCore import Qt

from .ai_assistant import AIRequestThread
from .world_state_builder import (
    get_previous_world_state,
    get_world_state_at,
    build_world_state_prompt,
    parse_world_state_response,
    save_world_state,
    format_world_state_for_display,
)


class WorldStateDialog(LiteraryDialog):
    def __init__(self, project, ai_config, vol_idx, ch_idx, parent=None):
        super().__init__(parent)
        self.project = project
        self.ai_config = ai_config
        self.vol_idx = vol_idx
        self.ch_idx = ch_idx
        self._thread = None
        self._cancelled = False
        self._new_state = None
        self._applied = False

        vol = project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]

        self.setWindowTitle(f"生成世界状态：第{vol_idx + 1}卷 第{ch_idx + 1}章《{ch.title}》")
        self.resize(1200, 850)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "基于本章正文与上一版世界状态，由 AI 生成【截至本章末尾】的状态快照。"
            "确认后写入项目。"
        ))

        splitter = QSplitter(Qt.Horizontal)

        # 左：上一版状态
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("<b>上一版状态（参考）</b>"))

        self.prev_view = QPlainTextEdit()
        self.prev_view.setReadOnly(True)
        prev_state = get_previous_world_state(project, vol_idx, ch_idx)
        if prev_state:
            self.prev_view.setPlainText(format_world_state_for_display(prev_state))
        else:
            self.prev_view.setPlainText("（这是本书第一章，无上一版状态）")
        left_layout.addWidget(self.prev_view)
        splitter.addWidget(left)

        # 右：新生成状态
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("<b>新状态（可编辑）</b>"))

        self.new_view = QPlainTextEdit()
        self.new_view.setPlaceholderText("点击「开始生成」后，AI 生成的新状态将显示在这里...")
        # 若已有本版状态，直接展示
        existing = get_world_state_at(project, vol_idx, ch_idx)
        if existing:
            self.new_view.setPlainText(format_world_state_for_display(existing))
        right_layout.addWidget(self.new_view)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        # 进度与状态
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel("准备就绪")
        self.status_label.setProperty("role", "hint")
        layout.addWidget(self.status_label)

        # 按钮
        bottom = QHBoxLayout()
        bottom.addStretch()

        self.start_btn = QPushButton("开始生成")
        self.start_btn.clicked.connect(self._start)
        bottom.addWidget(self.start_btn)

        self.apply_btn = QPushButton("写入项目")
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self._apply)
        bottom.addWidget(self.apply_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(close_btn)

        layout.addLayout(bottom)

    def _start(self):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "正在生成中...")
            return

        vol = self.project.volumes[self.vol_idx]
        ch = vol.chapters[self.ch_idx]

        content = (ch.content or "").strip()
        if not content:
            QMessageBox.information(
                self, "提示",
                "本章正文为空，无法提取世界状态。\n"
                "请先完成本章写作。"
            )
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(
                self, "提示",
                "审核 Agent 与策划 Agent 都未配置 API Key，无法生成。"
            )
            return

        prev_state = get_previous_world_state(
            self.project, self.vol_idx, self.ch_idx
        )
        prompt = build_world_state_prompt(
            self.project, self.vol_idx, self.ch_idx,
            prev_state, content, ch.summary
        )

        self.progress.show()
        self.status_label.setText("正在生成...")
        self.start_btn.setEnabled(False)
        self.apply_btn.setEnabled(False)

        self._thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*4, json_mode=True, timeout=120,
        )
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_finished(self, text):
        self._thread = None
        self.progress.hide()

        try:
            state = parse_world_state_response(text, self.vol_idx, self.ch_idx)
        except Exception as e:
            self.status_label.setText(f"解析失败：{e}")
            self.start_btn.setEnabled(True)
            QMessageBox.warning(self, "解析失败", f"AI 输出解析失败：{e}")
            return

        self._new_state = state
        self.new_view.setPlainText(format_world_state_for_display(state))
        self.status_label.setText(
            f"生成完成：{len(state.character_states)} 个角色 / "
            f"{len(state.active_threads)} 条未收束情节线"
        )
        self.start_btn.setEnabled(True)
        self.apply_btn.setEnabled(True)

    def _on_error(self, err):
        self._thread = None
        self.progress.hide()
        self.start_btn.setEnabled(True)
        self.status_label.setText(f"生成失败：{err}")
        QMessageBox.warning(self, "生成失败", err)

    def _apply(self):
        if not self._new_state:
            return
        save_world_state(self.project, self._new_state)
        self._applied = True
        QMessageBox.information(
            self, "已写入",
            "世界状态已写入项目。保存项目后持久化。"
        )
        self.accept()

    def _on_cancel(self):
        self._cancelled = True
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        self.reject()

    def reject(self):
        self._cancelled = True
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        super().reject()

    def closeEvent(self, event):
        self._on_cancel()
        super().closeEvent(event)

    def was_applied(self):
        return self._applied