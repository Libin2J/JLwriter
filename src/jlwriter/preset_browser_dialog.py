"""
预设书架对话框：网格卡片布局，hover 高亮，点击选中
"""
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QWidget, QGridLayout, QFrame, QLineEdit, QMessageBox, QComboBox
)
from .ui.tokens import SPACING
from .ui.widgets.section import EmptyState, HintBox
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont

from .preset_loader import load_presets
from .ui.base_dialog import BaseDialog


class PresetCard(QFrame):
    """单个预设卡片"""
    clicked = pyqtSignal(dict)
    right_clicked = pyqtSignal(dict)  # 新增

    def __init__(self, preset, parent=None):
        super().__init__(parent)
        self.preset = preset
        self.setFixedSize(230, 190)
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("role", "preset-card")
        self.setProperty("hover", "false")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        # 头部：图标 + 名称
        head = QHBoxLayout()
        head.setSpacing(6)

        icon_label = QLabel(preset.get("icon", "📖"))
        icon_font = QFont()
        icon_font.setPointSize(24)
        icon_label.setFont(icon_font)
        head.addWidget(icon_label)

        name_label = QLabel(preset.get("name", "未命名"))
        name_font = QFont()
        name_font.setPointSize(12)
        name_font.setBold(True)
        name_label.setFont(name_font)
        head.addWidget(name_label, 1)
        layout.addLayout(head)

        # 标签行
        tags = []
        for k in ("genre", "theme", "tone"):
            v = preset.get(k, "")
            if v:
                tags.append(str(v))
        if tags:
            tag_label = QLabel(" · ".join(tags[:3]))
            tag_label.setProperty("role", "tag")

        # 描述
        desc = preset.get("description", "")
        desc_label = QLabel(desc)
        desc_label.setProperty("role", "caption")
        desc_label.setWordWrap(True)
        desc_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        layout.addWidget(desc_label, 1)

        # 底部信息
        length_text = preset.get("target_length", "")
        vols = preset.get("volume_count", "")
        info_parts = []
        if length_text:
            info_parts.append(str(length_text))
        if vols:
            info_parts.append(f"{vols}卷")
        if info_parts:
            info_label = QLabel(" · ".join(info_parts))
            info_label.setProperty("role", "hint")
            layout.addWidget(info_label)

    def _apply_style(self, hover):
        from .ui.literary import repolish

        self.setProperty("hover", "true" if hover else "false")
        repolish(self)

    def enterEvent(self, event):
        self._apply_style(hover=True)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._apply_style(hover=False)
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.preset)
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        self.right_clicked.emit(self.preset)


class PresetBrowserDialog(BaseDialog):
    def __init__(self, parent=None):
        self.selected_preset = None

        super().__init__(
            parent,
            title="预设书架",
            subtitle="选择一个预设，一键填入题材 / 主题 / 基调等选项",
            default_size=(1100, 800),
            min_size=(760, 560),
            show_button_bar=False,
        )

        self.all_presets = load_presets()
        self._render_presets(self.all_presets)

    def build_content(self, layout):
        # 搜索
        search_row = QHBoxLayout()
        search_row.addStretch()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索预设...")
        self.search_edit.setMaximumWidth(240)
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.textChanged.connect(self._on_search)
        search_row.addWidget(self.search_edit)
        layout.addLayout(search_row)

        # 滚动区
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet(
            "QScrollArea { border: none; background: transparent; }"
        )

        self.cards_container = QWidget()
        self.cards_layout = QGridLayout(self.cards_container)
        self.cards_layout.setSpacing(SPACING.lg)
        self.cards_layout.setContentsMargins(
            SPACING.sm, SPACING.sm, SPACING.sm, SPACING.sm
        )
        self.cards_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.scroll.setWidget(self.cards_container)
        layout.addWidget(self.scroll, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bar.addWidget(close_btn)
        root_layout.addLayout(bar)

    def _render_presets(self, presets):
        # 清空旧卡片
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not presets:
            empty = EmptyState(
                "📚",
                "暂无预设",
                "可在项目根目录的 presetting.json 中添加自定义预设"
            )
            self.cards_layout.addWidget(empty, 0, 0, 1, 3)
            return

        cols = 3
        for i, preset in enumerate(presets):
            card = PresetCard(preset)
            card.clicked.connect(self._on_card_clicked)
            card.right_clicked.connect(self._on_card_right_clicked)  # 新增
            self.cards_layout.addWidget(card, i // cols, i % cols)

    def _on_card_right_clicked(self, preset):
        """用户预设允许删除；内置预设不可删"""
        from .preset_loader import is_user_preset, delete_user_preset
        if not is_user_preset(preset):
            return

        from PyQt5.QtWidgets import QMenu, QMessageBox
        from PyQt5.QtCore import QPoint

        menu = QMenu(self)
        action = menu.addAction(f"删除预设「{preset.get('name', '')}」")
        chosen = menu.exec_(self.mapToGlobal(QPoint(0, 0)))
        if chosen != action:
            return

        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除预设「{preset.get('name', '')}」吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        if delete_user_preset(preset.get("id", "")):
            self.all_presets = load_presets()
            self._render_presets(self.all_presets)

    def _on_search(self, text):
        text = (text or "").strip().lower()
        if not text:
            self._render_presets(self.all_presets)
            return

        filtered = []
        for p in self.all_presets:
            haystack = " ".join([
                str(p.get("name", "")),
                str(p.get("genre", "")),
                str(p.get("theme", "")),
                str(p.get("tone", "")),
                str(p.get("description", "")),
                str(p.get("user_notes", "")),
            ]).lower()
            if text in haystack:
                filtered.append(p)
        self._render_presets(filtered)

    def _on_card_clicked(self, preset):
        self.selected_preset = preset
        self.accept()

    def get_selected(self):
        return self.selected_preset


PRESET_ICONS = [
    "📖", "🗡️", "🚀", "🔍", "🌃", "🐉", "⚔️", "📝",
    "🎭", "💡", "🌙", "⚡", "🔥", "❄️", "🌊", "🏰",
]

class SavePresetDialog(BaseDialog):
    def __init__(self, default_name="", parent=None):
        self._result = None
        super().__init__(
            parent,
            title="保存为预设",
            subtitle="将当前填写的预设保存，方便下次快速复用或反复生成（抽卡）",
            default_size=(480, 340),
            min_size=(400, 300),
            show_button_bar=False,
        )
        self.name_edit.setText(default_name)

    def build_content(self, layout):
        layout.addWidget(HintBox(
            "保存的预设会写入本地配置目录，不修改程序内置预设。\n"
            "同名预设将被覆盖；不同名则新增。"
        ))

        # 名称
        row = QHBoxLayout()
        row.setSpacing(SPACING.md)
        label = QLabel("预设名称:")
        label.setMinimumWidth(80)
        row.addWidget(label)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("如：玄幻抽卡 A / 都市异能-紧凑")
        row.addWidget(self.name_edit, 1)
        layout.addLayout(row)

        # 图标
        row = QHBoxLayout()
        row.setSpacing(SPACING.md)
        label = QLabel("图标:")
        label.setMinimumWidth(80)
        row.addWidget(label)
        self.icon_combo = QComboBox()
        self.icon_combo.setEditable(True)
        self.icon_combo.setInsertPolicy(QComboBox.NoInsert)
        self.icon_combo.addItems(PRESET_ICONS)
        self.icon_combo.setCurrentText("📖")
        row.addWidget(self.icon_combo, 1)
        layout.addLayout(row)

        # 简介
        row = QHBoxLayout()
        row.setSpacing(SPACING.md)
        label = QLabel("简介:")
        label.setMinimumWidth(80)
        row.addWidget(label)
        self.desc_edit = QLineEdit()
        self.desc_edit.setPlaceholderText("可选，一句话描述这个预设的特点")
        row.addWidget(self.desc_edit, 1)
        layout.addLayout(row)

        layout.addStretch()

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)
        bar.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bar.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setProperty("role", "primary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        bar.addWidget(save_btn)

        root_layout.addLayout(bar)

    def _on_save(self):
        name = self.name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "预设名称不能为空。")
            return

        icon = self.icon_combo.currentText().strip() or "📖"
        description = self.desc_edit.text().strip()

        self._result = {
            "name": name,
            "icon": icon,
            "description": description,
        }
        self.accept()

    def get_result(self):
        return self._result
