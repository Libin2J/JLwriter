"""
策划初始化选择对话框：检测到项目已有设定时，让用户选择载入或重新开始
"""
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QListWidget, QListWidgetItem
from PyQt5.QtCore import Qt

from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ui.widgets.section import HintBox


# 阶段 ID -> 展示名
STAGE_LABELS = {
    "premise": "核心矛盾",
    "background": "故事背景",
    "power_system": "力量体系",
    "outline": "故事总纲",
    "characters": "关键人物",
    "organizations": "主要势力",
    "locations": "地图与地点",
    "items": "重要物品",
    "monsters": "怪物设计",       # 新增
}


class PlannerInitChoiceDialog(BaseDialog):
    """
    返回值：
    - "load"：载入已有设定，进入工作区
    - "fresh"：清空重新开始，进入预设页
    - 用户关闭：调用方应 reject 整个 planner
    """

    def __init__(self, existing_summary: dict, parent=None):
        """
        existing_summary: {stage_id: 简短摘要文本}
        """
        self._choice = None
        self._summary = existing_summary

        super().__init__(
            parent,
            title="检测到已有设定",
            subtitle="当前项目已包含部分策划内容，请选择下一步操作",
            default_size=(560, 520),
            min_size=(460, 420),
            show_button_bar=False,
        )

    def build_content(self, layout):
        layout.addWidget(HintBox(
            "「载入已有设定」会把项目当前的内容填入策划页面，"
            "你可以逐阶段查看、局部优化或完整重生成；"
            "「清空重新开始」会忽略现有内容，从预设页重新跑一遍流程（"
            "注意：不会删除项目已保存的内容，只是策划过程中不使用）。"
        ))

        overview = QLabel("现有内容概览")
        overview.setProperty("role", "field-label")
        layout.addWidget(overview)
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.NoSelection)
        self.list_widget.setFocusPolicy(Qt.NoFocus)

        for sid, label in STAGE_LABELS.items():
            text = self._summary.get(sid, "").strip()
            if text:
                item = QListWidgetItem(f"●  {label}   ·   {text}")
            else:
                item = QListWidgetItem(f"○  {label}（未填写）")
            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)
        bar.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bar.addWidget(cancel_btn)

        fresh_btn = QPushButton("清空重新开始")
        fresh_btn.clicked.connect(lambda: self._choose("fresh"))
        bar.addWidget(fresh_btn)

        load_btn = QPushButton("载入已有设定")
        load_btn.setProperty("role", "primary")
        load_btn.setDefault(True)
        load_btn.clicked.connect(lambda: self._choose("load"))
        bar.addWidget(load_btn)

        root_layout.addLayout(bar)

    def _choose(self, choice: str):
        self._choice = choice
        self.accept()

    def get_choice(self):
        return self._choice