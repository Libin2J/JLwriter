"""
重新生成阶段对话框：让用户选择完全重生成或基于现有内容优化
"""
from PyQt5.QtWidgets import QHBoxLayout, QPushButton, QPlainTextEdit, QRadioButton, QButtonGroup, QMessageBox

from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ui.widgets.section import HintBox


class RegenerateStageDialog(BaseDialog):
    """
    返回 (mode, guidance)：
    - mode="fresh"：完全重新生成
    - mode="optimize"：基于现有内容优化，guidance 为优化指引
    """

    def __init__(self, stage_label: str,
                 has_content: bool,
                 downstream_stages: list,
                 parent=None,
                 extra_fresh_hint: str = ""):
        """
        stage_label: 当前阶段名称（用于标题提示）
        has_content: 当前阶段是否已有内容
        downstream_stages: 下游已完成阶段的名称列表（用于警告）
        """
        self._mode = None
        self._guidance = ""
        self._stage_label = stage_label
        self._has_content = has_content
        self._downstream = downstream_stages
        self._extra_fresh_hint = (extra_fresh_hint or "").strip()

        super().__init__(
            parent,
            title=f"重新生成：{stage_label}",
            subtitle="选择生成方式",
            default_size=(620, 520),
            min_size=(520, 440),
            show_button_bar=False,
        )

    def build_content(self, layout):
        self.mode_group = QButtonGroup(self)

        # ---- 完全重新生成 ----
        self.fresh_radio = QRadioButton("完全重新生成")
        self.mode_group.addButton(self.fresh_radio)
        layout.addWidget(self.fresh_radio)

        fresh_hint_lines = [
            "丢弃当前阶段内容，让 AI 从头生成。",
        ]
        if self._downstream:
            names = "、".join(self._downstream)
            fresh_hint_lines.append(
                f"注意：下游已完成的 {len(self._downstream)} 个阶段"
                f"（{names}）也会被清除，"
                f"并随流水线重新生成。"
            )
        if self._extra_fresh_hint:
            fresh_hint_lines.append(self._extra_fresh_hint)

        layout.addWidget(HintBox(" ".join(fresh_hint_lines)))

        layout.addSpacing(SPACING.md)

        # ---- 基于现有内容优化 ----
        self.optimize_radio = QRadioButton("基于现有内容优化")
        self.mode_group.addButton(self.optimize_radio)
        layout.addWidget(self.optimize_radio)

        if not self._has_content:
            self.optimize_radio.setEnabled(False)
            layout.addWidget(HintBox(
                "当前阶段没有内容，无法优化；请选择完全重新生成。"
            ))
        else:
            layout.addWidget(HintBox(
                "保留当前内容，根据下方指引进行局部优化。"
                "不会影响下游阶段。"
            ))

        self.guidance_edit = QPlainTextEdit()
        self.guidance_edit.setPlaceholderText(
            "例如：\n"
            "· 开头太啰嗦，压缩到 300 字以内\n"
            "· 把主角目标写得更明确一些\n"
            "· 增加一个明确的阻碍，让冲突更尖锐\n"
            "· 保留现有结构，只把语言精炼一下"
        )
        self.guidance_edit.setMinimumHeight(140)
        layout.addWidget(self.guidance_edit)

        self.guidance_edit.setEnabled(False)

        # 默认选择
        if self._has_content:
            self.fresh_radio.setChecked(True)
        else:
            self.fresh_radio.setChecked(True)

        self.mode_group.buttonToggled.connect(self._on_mode_toggled)

    def _on_mode_toggled(self, btn, checked):
        if not checked:
            return
        self.guidance_edit.setEnabled(
            self.optimize_radio.isChecked()
        )

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)
        bar.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bar.addWidget(cancel_btn)

        ok_btn = QPushButton("开始")
        ok_btn.setProperty("role", "primary")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(self._on_ok)
        bar.addWidget(ok_btn)

        root_layout.addLayout(bar)

    def _on_ok(self):
        if self.fresh_radio.isChecked():
            self._mode = "fresh"
            self._guidance = ""
            self.accept()
            return

        # 优化模式
        if not self._has_content:
            QMessageBox.warning(
                self, "提示",
                "当前阶段没有内容，无法优化。"
            )
            return

        guidance = self.guidance_edit.toPlainText().strip()
        if not guidance:
            QMessageBox.warning(
                self, "提示",
                "请填写优化指引（例如：开头太啰嗦，压缩到 300 字以内 / 某卷大纲节奏太平淡，需要增加冲突）。"
            )
            return

        self._mode = "optimize"
        self._guidance = guidance
        self.accept()

    def get_result(self):
        return self._mode, self._guidance