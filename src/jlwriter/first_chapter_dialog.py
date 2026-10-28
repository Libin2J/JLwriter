"""
首章生成对话框：接受策划后自动生成第一卷第一章
"""
from .ui.literary import LiteraryDialog
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QMessageBox
from PyQt5.QtGui import QTextCursor

from .ai_assistant import AIRequestThread


class FirstChapterDialog(LiteraryDialog):
    def __init__(self, project, ai_config, parent=None,
                 volume_title="第一卷", chapter_title="第一章"):
        super().__init__(parent)
        self.project = project
        self.ai_config = ai_config
        self._thread = None
        self._streaming_started = False
        self._accepted = False
        self._target_volume = None
        self._target_chapter = None

        self.setWindowTitle("生成首章")
        self.resize(1100, 850)

        layout = QVBoxLayout(self)

        # ---- 卷名 / 章名 ----
        row = QHBoxLayout()
        row.addWidget(QLabel("卷名:"))
        self.volume_edit = QLineEdit(volume_title)
        row.addWidget(self.volume_edit, 1)
        row.addWidget(QLabel("章名:"))
        self.chapter_edit = QLineEdit(chapter_title)
        row.addWidget(self.chapter_edit, 1)
        layout.addLayout(row)

        # ---- 写作提示（可编辑）----
        layout.addWidget(QLabel("写作提示（可编辑，用于指导 AI 生成）："))
        self.prompt_edit = QPlainTextEdit()
        self.prompt_edit.setPlainText(self._build_default_prompt())
        self.prompt_edit.setMinimumHeight(160)
        layout.addWidget(self.prompt_edit)

        # ---- 正文预览 ----
        layout.addWidget(QLabel("正文预览（生成后可编辑，接受时以此内容为准）："))
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("点击「开始生成」后，AI 将流式输出正文...")
        layout.addWidget(self.content_edit, 1)

        # ---- 状态 ----
        self.status_label = QLabel("准备就绪")
        self.status_label.setProperty("role", "hint")
        layout.addWidget(self.status_label)

        # ---- 按钮 ----
        btn_row = QHBoxLayout()
        self.start_btn = QPushButton("开始生成")
        self.start_btn.clicked.connect(self._start_generation)
        btn_row.addWidget(self.start_btn)

        self.regen_btn = QPushButton("重新生成")
        self.regen_btn.clicked.connect(self._start_generation)
        self.regen_btn.setEnabled(False)
        btn_row.addWidget(self.regen_btn)

        btn_row.addStretch()

        self.accept_btn = QPushButton("接受并保存到正文")
        self.accept_btn.clicked.connect(self._accept_and_save)
        self.accept_btn.setEnabled(False)
        btn_row.addWidget(self.accept_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(cancel_btn)

        layout.addLayout(btn_row)

    # ---------------- Prompt 构建 ----------------
    def _build_default_prompt(self):
        project = self.project
        parts = []

        # 章节规划（优先使用）
        vol = project.volumes[0] if project.volumes else None
        ch = vol.chapters[0] if vol and vol.chapters else None
        if ch and ch.plan:
            parts.append(f"##本章规划\n{ch.plan.to_prompt_text()}")

        if project.premise:
            parts.append(f"##核心矛盾\n{project.premise}")
        if project.story_background:
            parts.append(f"##故事背景\n{project.story_background}")
        if project.power_system:
            parts.append(f"##力量体系\n{project.power_system}")
        if project.outline:
            parts.append(f"##故事总纲\n{project.outline}")

        # ... 其余角色、势力、地点不变 ...

        parts.append(
            "##任务\n"
            "请撰写第一卷第一章的正文。要求：\n"
            "1. 严格按【本章规划】的章节目标、关键事件、结尾钩子推进\n"
            "2. 只引入本章规划中列出的出场人物，不要提前引入其他角色\n"
            "3. 只释放本章规划中列出的信息，不要一次性倾倒设定\n"
            "4. 结尾落在规划指定的钩子上\n"
            "5. 篇幅 2000-3000 字\n"
            "6. 只输出正文，不要标题、解释或任何额外说明"
        )
        return "\n\n".join(parts)

    # ---------------- 生成 ----------------
    def _start_generation(self):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "正在生成中...")
            return

        resolved = self.ai_config.resolve_agent("writer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "写作 Agent 未配置 API Key。")
            return

        prompt = self.prompt_edit.toPlainText().strip()
        if not prompt:
            QMessageBox.warning(self, "提示", "写作提示不能为空。")
            return

        self._streaming_started = False
        self.content_edit.clear()
        self.status_label.setText("正在生成...")
        self.start_btn.setEnabled(False)
        self.regen_btn.setEnabled(False)
        self.accept_btn.setEnabled(False)

        self._thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*4, timeout=240,
        )
        self._thread.chunk.connect(self._on_chunk)
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_chunk(self, text):
        if not self._streaming_started:
            self.content_edit.clear()
            self._streaming_started = True
        cursor = self.content_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.content_edit.setTextCursor(cursor)
        self.content_edit.ensureCursorVisible()

    def _on_finished(self, text):
        self._thread = None
        if not self._streaming_started:
            self.content_edit.setPlainText(text)
        final_text = self.content_edit.toPlainText()
        self.status_label.setText(f"生成完成，共 {len(final_text)} 字")
        self.start_btn.setEnabled(True)
        self.regen_btn.setEnabled(True)
        self.accept_btn.setEnabled(True)

    def _on_error(self, err):
        self._thread = None
        self.status_label.setText(f"生成失败：{err}")
        self.start_btn.setEnabled(True)
        self.regen_btn.setEnabled(True)

    # ---------------- 保存 ----------------
    def _accept_and_save(self):
        content = self.content_edit.toPlainText().strip()
        if not content:
            QMessageBox.warning(self, "提示", "正文为空，无法保存。")
            return

        vol_title = self.volume_edit.text().strip() or "第一卷"
        ch_title = self.chapter_edit.text().strip() or "第一章"

        from .models import Volume, Chapter
        if not self.project.volumes:
            self.project.volumes.append(Volume(title=vol_title))
        else:
            self.project.volumes[0].title = vol_title
        vol = self.project.volumes[0]
        if not vol.chapters:
            vol.chapters.append(Chapter(title=ch_title))
        else:
            vol.chapters[0].title = ch_title
        ch = vol.chapters[0]
        ch.content = content

        self._accepted = True
        self._target_volume = vol
        self._target_chapter = ch
        self.accept()

    def _on_cancel(self):
        if self._thread and self._thread.isRunning():
            reply = QMessageBox.question(
                self, "确认取消",
                "生成还在进行，取消将丢弃当前内容。是否继续？"
            )
            if reply != QMessageBox.Yes:
                return
            self._thread.quit()
            self._thread.wait(1000)
        self.reject()

    def get_result(self):
        """返回 (vol, ch)，未接受则为 (None, None)"""
        if self._accepted:
            return self._target_volume, self._target_chapter
        return None, None