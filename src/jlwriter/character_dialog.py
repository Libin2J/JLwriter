"""
故事档案：角色 / 地点 / 物品 / 势力 / 怪物 / 关系网络
"""
from PyQt5.QtWidgets import (
    QHBoxLayout, QVBoxLayout, QWidget, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QPlainTextEdit, QPushButton,
    QMessageBox, QTabWidget, QComboBox, QFormLayout, QGroupBox,
    QScrollArea, QFrame,
)
from PyQt5.QtCore import Qt
from .models import CharacterProfile, Location, Organization, Item, Monster
from .relation_editor import RelationTab

from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING


# ============================================================
# 通用档案编辑基类
# ============================================================
class _AssetTabBase(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self.current_profile = None

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(SPACING.md)

        # 左侧列表
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SPACING.sm)

        self.count_label = QLabel("列表")
        left_layout.addWidget(self.count_label)

        self.list_widget = QListWidget()
        self.list_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.currentItemChanged.connect(self._on_select)
        left_layout.addWidget(self.list_widget, 1)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(SPACING.sm)
        add_btn = QPushButton("新建")
        add_btn.clicked.connect(self._add_new)
        del_btn = QPushButton("删除")
        del_btn.setProperty("role", "danger")
        del_btn.clicked.connect(self._delete_current)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        left_layout.addLayout(btn_row)

        left_widget.setMaximumWidth(260)
        main_layout.addWidget(left_widget)

        # 右侧编辑区：独立滚动，避免字段把整个 tab 撑高
        self.right_widget = QWidget()
        self.right_layout = QVBoxLayout(self.right_widget)
        self.right_layout.setContentsMargins(0, 0, 0, 0)
        self.right_layout.setSpacing(SPACING.sm)
        self._build_editor()
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setFrameShape(QFrame.NoFrame)
        self.right_scroll.setWidget(self.right_widget)
        self.right_scroll.viewport().setAutoFillBackground(False)
        main_layout.addWidget(self.right_scroll, 1)

        self._refresh_list()

    def _get_collection(self):
        raise NotImplementedError

    def _get_collection_name(self):
        raise NotImplementedError

    def _build_editor(self):
        raise NotImplementedError

    def _load_fields(self, profile):
        raise NotImplementedError

    def _clear_fields(self):
        raise NotImplementedError

    def _block_signals(self, blocked):
        raise NotImplementedError

    def _create_new_profile(self):
        raise NotImplementedError

    def _get_display_name(self, profile):
        return profile.name

    def _on_field_changed(self):
        pass

    def _refresh_list(self, keep_name=None):
        collection = self._get_collection()
        self.list_widget.blockSignals(True)
        self.list_widget.clear()
        for profile in collection:
            item = QListWidgetItem(self._get_display_name(profile))
            item.setData(Qt.UserRole, profile)
            self.list_widget.addItem(item)
        self.list_widget.blockSignals(False)

        self.count_label.setText(
            f"{self._get_collection_name()}（共 {len(collection)} 条）"
        )

        if self.list_widget.count() > 0:
            target_row = 0
            if keep_name:
                for i in range(self.list_widget.count()):
                    if self.list_widget.item(i).text() == keep_name:
                        target_row = i
                        break
            self.list_widget.setCurrentRow(target_row)
        else:
            self.current_profile = None
            self._clear_fields()

    def _on_select(self, current, previous):
        if current is None:
            self.current_profile = None
            self._clear_fields()
            return
        self.current_profile = current.data(Qt.UserRole)
        self._load_fields(self.current_profile)

    def _add_new(self):
        collection = self._get_collection()
        base_name = "新档案"
        name = base_name
        i = 1
        existing = {p.name for p in collection}
        while name in existing:
            i += 1
            name = f"{base_name}{i}"

        profile = self._create_new_profile(name)
        collection.append(profile)

        item = QListWidgetItem(profile.name)
        item.setData(Qt.UserRole, profile)
        self.list_widget.addItem(item)
        self.list_widget.setCurrentItem(item)
        self.count_label.setText(
            f"{self._get_collection_name()}（共 {len(collection)} 条）"
        )

    def _delete_current(self):
        if not self.current_profile:
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除「{self.current_profile.name}」吗？此操作不可撤销。"
        )
        if reply != QMessageBox.Yes:
            return
        self._get_collection().remove(self.current_profile)
        self._refresh_list()

    def refresh(self):
        keep_name = self.current_profile.name if self.current_profile else None
        self._refresh_list(keep_name=keep_name)


# ============================================================
# 角色
# ============================================================
class CharacterTab(_AssetTabBase):
    def _get_collection(self):
        return self.project.characters

    def _get_collection_name(self):
        return "角色列表"

    def _create_new_profile(self, name):
        return CharacterProfile(name=name)

    def _build_editor(self):
        self.right_layout.addWidget(QLabel("姓名"))
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.right_layout.addWidget(self.name_edit)

        self.right_layout.addWidget(QLabel("别名（多个用顿号、或逗号分隔）"))
        self.aliases_edit = QLineEdit()
        self.aliases_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.aliases_edit)

        self.right_layout.addWidget(QLabel("外貌"))
        self.appearance_edit = QPlainTextEdit()
        self.appearance_edit.setMaximumHeight(70)
        self.appearance_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.appearance_edit)

        self.right_layout.addWidget(QLabel("性格"))
        self.personality_edit = QPlainTextEdit()
        self.personality_edit.setMaximumHeight(70)
        self.personality_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.personality_edit)

        self.right_layout.addWidget(QLabel("习惯（语言习惯和习惯性动作）"))
        self.habits_edit = QPlainTextEdit()
        self.habits_edit.setMaximumHeight(70)
        self.habits_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.habits_edit)

        # ---------- 当前状态（最新） ----------
        status_group = QGroupBox("当前状态（最新）")
        status_form = QFormLayout(status_group)
        status_form.setSpacing(SPACING.sm)

        self.age_edit = QLineEdit()
        self.age_edit.setPlaceholderText("如：23 岁 / 约四十岁 / 不老")
        self.age_edit.textChanged.connect(self._on_field_changed)
        status_form.addRow("年龄:", self.age_edit)

        self.power_edit = QLineEdit()
        self.power_edit.setPlaceholderText("如：筑基中期 / 三阶火系法师")
        self.power_edit.textChanged.connect(self._on_field_changed)
        status_form.addRow("力量等级:", self.power_edit)

        self.emotion_edit = QPlainTextEdit()
        self.emotion_edit.setMaximumHeight(70)
        self.emotion_edit.setPlaceholderText(
            "如：对师父充满感激；对师兄暗藏敌意；对即将来临的试炼感到不安"
        )
        self.emotion_edit.textChanged.connect(self._on_field_changed)
        status_form.addRow("情绪:", self.emotion_edit)

        self.health_edit = QLineEdit()
        self.health_edit.setPlaceholderText(
            "如：健康 / 左臂受伤未愈 / 中毒昏迷 / 濒死 / 已死亡"
        )
        self.health_edit.textChanged.connect(self._on_field_changed)
        status_form.addRow("健康状况:", self.health_edit)

        self.status_notes_edit = QPlainTextEdit()
        self.status_notes_edit.setMaximumHeight(60)
        self.status_notes_edit.setPlaceholderText(
            "其他需要记录的状态信息，如所在地、当前目标、随身物品等"
        )
        self.status_notes_edit.textChanged.connect(self._on_field_changed)
        status_form.addRow("其他:", self.status_notes_edit)

        self.right_layout.addWidget(status_group)

        self.right_layout.addWidget(QLabel("时间线（每行一个事件）"))
        self.timeline_edit = QPlainTextEdit()
        self.timeline_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.timeline_edit)

    def _load_fields(self, profile):
        self._block_signals(True)
        self.name_edit.setText(profile.name)
        self.aliases_edit.setText("、".join(profile.aliases))
        self.appearance_edit.setPlainText(profile.appearance)
        self.personality_edit.setPlainText(profile.personality)
        self.habits_edit.setPlainText(profile.habits)
        self.age_edit.setText(profile.age or "")
        self.power_edit.setText(profile.power_level or "")
        self.emotion_edit.setPlainText(profile.emotion or "")
        self.health_edit.setText(profile.health or "")
        self.status_notes_edit.setPlainText(profile.status_notes or "")
        self.timeline_edit.setPlainText("\n".join(profile.timeline))
        self._block_signals(False)

    def _clear_fields(self):
        self._block_signals(True)
        self.name_edit.clear()
        self.aliases_edit.clear()
        self.appearance_edit.clear()
        self.personality_edit.clear()
        self.habits_edit.clear()
        self.age_edit.clear()
        self.power_edit.clear()
        self.emotion_edit.clear()
        self.health_edit.clear()
        self.status_notes_edit.clear()
        self.timeline_edit.clear()
        self._block_signals(False)

    def _block_signals(self, blocked):
        self.name_edit.blockSignals(blocked)
        self.aliases_edit.blockSignals(blocked)
        self.appearance_edit.blockSignals(blocked)
        self.personality_edit.blockSignals(blocked)
        self.habits_edit.blockSignals(blocked)
        # 新增
        self.age_edit.blockSignals(blocked)
        self.power_edit.blockSignals(blocked)
        self.emotion_edit.blockSignals(blocked)
        self.health_edit.blockSignals(blocked)
        self.status_notes_edit.blockSignals(blocked)
        self.timeline_edit.blockSignals(blocked)

    def _on_field_changed(self):
        if not self.current_profile:
            return
        self.current_profile.appearance = self.appearance_edit.toPlainText()
        self.current_profile.personality = (
            self.personality_edit.toPlainText()
        )
        self.current_profile.habits = self.habits_edit.toPlainText()
        self.current_profile.age = self.age_edit.text().strip()
        self.current_profile.power_level = self.power_edit.text().strip()
        self.current_profile.emotion = self.emotion_edit.toPlainText()
        self.current_profile.health = self.health_edit.text().strip()
        self.current_profile.status_notes = (
            self.status_notes_edit.toPlainText()
        )
        self.current_profile.timeline = [
            line for line in self.timeline_edit.toPlainText().splitlines()
            if line.strip()
        ]
        raw = self.aliases_edit.text()
        parts = []
        for sep in ("、", ",", "，", ";", "；"):
            if sep in raw:
                parts = [p.strip() for p in raw.split(sep) if p.strip()]
                break
        else:
            parts = [raw.strip()] if raw.strip() else []
        seen = []
        for p in parts:
            if p and p != self.current_profile.name and p not in seen:
                seen.append(p)
        self.current_profile.aliases = seen

    def _on_name_changed(self):
        if not self.current_profile:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.name_edit.setText(self.current_profile.name)
            return
        if new_name == self.current_profile.name:
            return
        for c in self.project.characters:
            if c is not self.current_profile and c.name == new_name:
                QMessageBox.warning(self, "重名",
                                    f"已存在名为「{new_name}」的角色。")
                self.name_edit.setText(self.current_profile.name)
                return
        self.current_profile.name = new_name
        cur = self.list_widget.currentItem()
        if cur:
            cur.setText(new_name)


# ============================================================
# 地点
# ============================================================
LOCATION_LEVELS = ["大陆", "国家", "地区", "城市", "村镇",
                   "建筑", "秘境", "其他"]


class LocationTab(_AssetTabBase):
    def _get_collection(self):
        return self.project.locations

    def _get_collection_name(self):
        return "地点列表"

    def _create_new_profile(self, name):
        return Location(name=name)

    def _build_editor(self):
        self.right_layout.addWidget(QLabel("名称"))
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.right_layout.addWidget(self.name_edit)

        self.right_layout.addWidget(QLabel("层级"))
        self.level_combo = QComboBox()
        self.level_combo.setEditable(True)
        self.level_combo.addItems(LOCATION_LEVELS)
        self.level_combo.currentTextChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.level_combo)

        self.right_layout.addWidget(QLabel("上级地点（可选）"))
        self.parent_edit = QLineEdit()
        self.parent_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.parent_edit)

        self.right_layout.addWidget(QLabel("描述"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.desc_edit)

        self.hint_label = QLabel("")
        self.hint_label.setProperty("role", "hint")
        self.hint_label.setWordWrap(True)
        self.right_layout.addWidget(self.hint_label)

    def _load_fields(self, location):
        self._block_signals(True)
        self.name_edit.setText(location.name)
        self.level_combo.setCurrentText(location.level or "")
        self.parent_edit.setText(location.parent or "")
        self.desc_edit.setPlainText(location.description or "")
        self._block_signals(False)
        self._update_hint(location)

    def _clear_fields(self):
        self._block_signals(True)
        self.name_edit.clear()
        self.level_combo.setCurrentText("")
        self.parent_edit.clear()
        self.desc_edit.clear()
        self._block_signals(False)
        self.hint_label.clear()

    def _block_signals(self, blocked):
        self.name_edit.blockSignals(blocked)
        self.level_combo.blockSignals(blocked)
        self.parent_edit.blockSignals(blocked)
        self.desc_edit.blockSignals(blocked)

    def _on_field_changed(self):
        if not self.current_profile:
            return
        self.current_profile.level = self.level_combo.currentText().strip()
        self.current_profile.parent = self.parent_edit.text().strip()
        self.current_profile.description = self.desc_edit.toPlainText()
        self._update_hint(self.current_profile)

    def _on_name_changed(self):
        if not self.current_profile:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.name_edit.setText(self.current_profile.name)
            return
        if new_name == self.current_profile.name:
            return
        for l in self.project.locations:
            if l is not self.current_profile and l.name == new_name:
                QMessageBox.warning(self, "重名",
                                    f"已存在名为「{new_name}」的地点。")
                self.name_edit.setText(self.current_profile.name)
                return
        old_name = self.current_profile.name
        self.current_profile.name = new_name
        cur = self.list_widget.currentItem()
        if cur:
            cur.setText(new_name)
        for l in self.project.locations:
            if l.parent == old_name:
                l.parent = new_name

    def _update_hint(self, location):
        if not location or not location.name:
            self.hint_label.clear()
            return
        children = [l.name for l in self.project.locations
                    if l.parent == location.name]
        lines = []
        if location.parent:
            lines.append(f"上级：{location.parent}")
        if children:
            lines.append(f"下辖：{'、'.join(children[:8])}")
        self.hint_label.setText("　｜　".join(lines))


# ============================================================
# 物品
# ============================================================
ITEM_TYPES = ["神器", "法宝", "道具", "武器", "装备", "丹药", "其他"]


class ItemTab(_AssetTabBase):
    def _get_collection(self):
        return self.project.items

    def _get_collection_name(self):
        return "物品列表"

    def _create_new_profile(self, name):
        return Item(name=name)

    def _build_editor(self):
        self.right_layout.addWidget(QLabel("名称"))
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.right_layout.addWidget(self.name_edit)

        self.right_layout.addWidget(QLabel("类型"))
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.addItems(ITEM_TYPES)
        self.type_combo.currentTextChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.type_combo)

        self.right_layout.addWidget(QLabel("描述"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setMaximumHeight(80)
        self.desc_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.desc_edit)

        self.right_layout.addWidget(QLabel("特殊能力"))
        self.ability_edit = QPlainTextEdit()
        self.ability_edit.setMaximumHeight(70)
        self.ability_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.ability_edit)

        self.right_layout.addWidget(QLabel("归属者"))
        self.owner_edit = QLineEdit()
        self.owner_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.owner_edit)

        self.hint_label = QLabel("")
        self.hint_label.setProperty("role", "hint")
        self.hint_label.setWordWrap(True)
        self.right_layout.addWidget(self.hint_label)

    def _load_fields(self, item):
        self._block_signals(True)
        self.name_edit.setText(item.name)
        self.type_combo.setCurrentText(item.type or "")
        self.desc_edit.setPlainText(item.description or "")
        self.ability_edit.setPlainText(item.ability or "")
        self.owner_edit.setText(item.owner or "")
        self._block_signals(False)
        self._update_hint(item)

    def _clear_fields(self):
        self._block_signals(True)
        self.name_edit.clear()
        self.type_combo.setCurrentText("")
        self.desc_edit.clear()
        self.ability_edit.clear()
        self.owner_edit.clear()
        self._block_signals(False)
        self.hint_label.clear()

    def _block_signals(self, blocked):
        self.name_edit.blockSignals(blocked)
        self.type_combo.blockSignals(blocked)
        self.desc_edit.blockSignals(blocked)
        self.ability_edit.blockSignals(blocked)
        self.owner_edit.blockSignals(blocked)

    def _on_field_changed(self):
        if not self.current_profile:
            return
        self.current_profile.type = self.type_combo.currentText().strip()
        self.current_profile.description = self.desc_edit.toPlainText()
        self.current_profile.ability = self.ability_edit.toPlainText()
        self.current_profile.owner = self.owner_edit.text().strip()
        self._update_hint(self.current_profile)

    def _on_name_changed(self):
        if not self.current_profile:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.name_edit.setText(self.current_profile.name)
            return
        if new_name == self.current_profile.name:
            return
        for it in self.project.items:
            if it is not self.current_profile and it.name == new_name:
                QMessageBox.warning(self, "重名",
                                    f"已存在名为「{new_name}」的物品。")
                self.name_edit.setText(self.current_profile.name)
                return
        self.current_profile.name = new_name
        cur = self.list_widget.currentItem()
        if cur:
            cur.setText(new_name)

    def _update_hint(self, item):
        if not item or not item.name:
            self.hint_label.clear()
            return
        lines = []
        if item.owner:
            char_names = {c.name for c in self.project.characters}
            org_names = {o.name for o in self.project.organizations}
            tag = ""
            if item.owner in char_names:
                tag = "（角色）"
            elif item.owner in org_names:
                tag = "（势力）"
            lines.append(f"归属：{item.owner}{tag}")
        self.hint_label.setText("　｜　".join(lines))


# ============================================================
# 势力
# ============================================================
ORGANIZATION_NATURES = ["门派", "家族", "王国", "教团",
                        "商会", "军队", "公司", "其他"]


class OrganizationTab(_AssetTabBase):
    def _get_collection(self):
        return self.project.organizations

    def _get_collection_name(self):
        return "势力列表"

    def _create_new_profile(self, name):
        return Organization(name=name)

    def _build_editor(self):
        self.right_layout.addWidget(QLabel("名称"))
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.right_layout.addWidget(self.name_edit)

        self.right_layout.addWidget(QLabel("性质"))
        self.nature_combo = QComboBox()
        self.nature_combo.setEditable(True)
        self.nature_combo.addItems(ORGANIZATION_NATURES)
        self.nature_combo.currentTextChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.nature_combo)

        self.right_layout.addWidget(QLabel("描述"))
        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setMaximumHeight(90)
        self.desc_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.desc_edit)

        self.right_layout.addWidget(QLabel("主要成员（每行一个名字）"))
        self.members_edit = QPlainTextEdit()
        self.members_edit.setMaximumHeight(90)
        self.members_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.members_edit)

        self.right_layout.addWidget(QLabel(
            "与其他势力的关系（每行一条：目标势力｜类型｜说明）"
        ))
        self.relations_edit = QPlainTextEdit()
        self.relations_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.relations_edit)

        self.hint_label = QLabel("")
        self.hint_label.setProperty("role", "hint")
        self.hint_label.setWordWrap(True)
        self.right_layout.addWidget(self.hint_label)

    def _load_fields(self, org):
        self._block_signals(True)
        self.name_edit.setText(org.name)
        self.nature_combo.setCurrentText(org.nature or "")
        self.desc_edit.setPlainText(org.description or "")
        self.members_edit.setPlainText("\n".join(org.members or []))
        rel_lines = []
        for r in org.relations or []:
            if not isinstance(r, dict):
                continue
            rel_lines.append(
                f"{r.get('to', '')}｜{r.get('type', '')}｜{r.get('description', '')}"
            )
        self.relations_edit.setPlainText("\n".join(rel_lines))
        self._block_signals(False)
        self._update_hint(org)

    def _clear_fields(self):
        self._block_signals(True)
        self.name_edit.clear()
        self.nature_combo.setCurrentText("")
        self.desc_edit.clear()
        self.members_edit.clear()
        self.relations_edit.clear()
        self._block_signals(False)
        self.hint_label.clear()

    def _block_signals(self, blocked):
        self.name_edit.blockSignals(blocked)
        self.nature_combo.blockSignals(blocked)
        self.desc_edit.blockSignals(blocked)
        self.members_edit.blockSignals(blocked)
        self.relations_edit.blockSignals(blocked)

    def _on_field_changed(self):
        if not self.current_profile:
            return
        self.current_profile.nature = self.nature_combo.currentText().strip()
        self.current_profile.description = self.desc_edit.toPlainText()
        self.current_profile.members = [
            line.strip() for line in self.members_edit.toPlainText().splitlines()
            if line.strip()
        ]
        new_rels = []
        for line in self.relations_edit.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            sep = "｜" if "｜" in line else ("|" if "|" in line else None)
            parts = [p.strip() for p in line.split(sep)] if sep else [line]
            to = parts[0] if len(parts) > 0 else ""
            typ = parts[1] if len(parts) > 1 else ""
            desc = parts[2] if len(parts) > 2 else ""
            if to:
                new_rels.append({"to": to, "type": typ, "description": desc})
        self.current_profile.relations = new_rels
        self._update_hint(self.current_profile)

    def _on_name_changed(self):
        if not self.current_profile:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.name_edit.setText(self.current_profile.name)
            return
        if new_name == self.current_profile.name:
            return
        for o in self.project.organizations:
            if o is not self.current_profile and o.name == new_name:
                QMessageBox.warning(self, "重名",
                                    f"已存在名为「{new_name}」的势力。")
                self.name_edit.setText(self.current_profile.name)
                return
        self.current_profile.name = new_name
        cur = self.list_widget.currentItem()
        if cur:
            cur.setText(new_name)

    def _update_hint(self, org):
        if not org or not org.name:
            self.hint_label.clear()
            return
        char_names = {c.name for c in self.project.characters}
        valid = [m for m in (org.members or []) if m in char_names]
        unknown = [m for m in (org.members or []) if m not in char_names]
        parts = []
        if valid:
            parts.append(f"已识别成员：{'、'.join(valid[:6])}")
        if unknown:
            parts.append(f"未匹配角色：{'、'.join(unknown[:6])}")
        self.hint_label.setText("　｜　".join(parts))


# ============================================================
# 怪物
# ============================================================
class MonsterTab(_AssetTabBase):
    def _get_collection(self):
        return self.project.monsters

    def _get_collection_name(self):
        return "怪物列表"

    def _create_new_profile(self, name):
        return Monster(name=name)

    def _build_editor(self):
        self.right_layout.addWidget(QLabel("名称"))
        self.name_edit = QLineEdit()
        self.name_edit.editingFinished.connect(self._on_name_changed)
        self.right_layout.addWidget(self.name_edit)

        self.right_layout.addWidget(QLabel("别名"))
        self.aliases_edit = QLineEdit()
        self.aliases_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.aliases_edit)

        self.right_layout.addWidget(QLabel("外形"))
        self.appearance_edit = QPlainTextEdit()
        self.appearance_edit.setMaximumHeight(90)
        self.appearance_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.appearance_edit)

        self.right_layout.addWidget(QLabel("行为与能力"))
        self.behavior_edit = QPlainTextEdit()
        self.behavior_edit.setMaximumHeight(110)
        self.behavior_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.behavior_edit)

        self.right_layout.addWidget(
            QLabel("纲目（可选，如：妖兽-蛇形-黑鳞蛟科）")
        )
        self.category_edit = QLineEdit()
        self.category_edit.textChanged.connect(self._on_field_changed)
        self.right_layout.addWidget(self.category_edit)

    def _load_fields(self, monster):
        self._block_signals(True)
        self.name_edit.setText(monster.name)
        self.aliases_edit.setText("、".join(monster.aliases))
        self.appearance_edit.setPlainText(monster.appearance)
        self.behavior_edit.setPlainText(monster.behavior_ability)
        self.category_edit.setText(monster.category)
        self._block_signals(False)

    def _clear_fields(self):
        self._block_signals(True)
        self.name_edit.clear()
        self.aliases_edit.clear()
        self.appearance_edit.clear()
        self.behavior_edit.clear()
        self.category_edit.clear()
        self._block_signals(False)

    def _block_signals(self, blocked):
        self.name_edit.blockSignals(blocked)
        self.aliases_edit.blockSignals(blocked)
        self.appearance_edit.blockSignals(blocked)
        self.behavior_edit.blockSignals(blocked)
        self.category_edit.blockSignals(blocked)

    def _on_field_changed(self):
        if not self.current_profile:
            return
        self.current_profile.appearance = self.appearance_edit.toPlainText()
        self.current_profile.behavior_ability = (
            self.behavior_edit.toPlainText()
        )
        self.current_profile.category = self.category_edit.text().strip()
        raw = self.aliases_edit.text()
        parts = []
        for sep in ("、", ",", "，", ";", "；"):
            if sep in raw:
                parts = [p.strip() for p in raw.split(sep) if p.strip()]
                break
        else:
            parts = [raw.strip()] if raw.strip() else []
        seen = []
        for p in parts:
            if p and p != self.current_profile.name and p not in seen:
                seen.append(p)
        self.current_profile.aliases = seen

    def _on_name_changed(self):
        if not self.current_profile:
            return
        new_name = self.name_edit.text().strip()
        if not new_name:
            self.name_edit.setText(self.current_profile.name)
            return
        if new_name == self.current_profile.name:
            return
        for m in self.project.monsters:
            if m is not self.current_profile and m.name == new_name:
                QMessageBox.warning(self, "重名",
                                    f"已存在名为「{new_name}」的怪物。")
                self.name_edit.setText(self.current_profile.name)
                return
        self.current_profile.name = new_name
        cur = self.list_widget.currentItem()
        if cur:
            cur.setText(new_name)


# ============================================================
# 主对话框
# ============================================================
class CharacterDialog(BaseDialog):
    def __init__(self, project, parent=None):
        self.project = project
        super().__init__(
            parent,
            title="故事档案",
            subtitle="管理角色、地点、物品、势力、怪物与关系网络",
            default_size=(1800, 1150),
            min_size=(900, 620),
            show_button_bar=False,
            scroll_body=False,
        )

    def build_content(self, layout):
        self.tabs = QTabWidget()
        self.character_tab = CharacterTab(self.project, self)
        self.location_tab = LocationTab(self.project, self)
        self.item_tab = ItemTab(self.project, self)
        self.org_tab = OrganizationTab(self.project, self)
        self.monster_tab = MonsterTab(self.project, self)
        self.relation_tab = RelationTab(self.project, self)

        self.tabs.addTab(self.character_tab, "角色档案")
        self.tabs.addTab(self.location_tab, "地点档案")
        self.tabs.addTab(self.item_tab, "物品档案")
        self.tabs.addTab(self.org_tab, "势力档案")
        self.tabs.addTab(self.monster_tab, "怪物档案")
        self.tabs.addTab(self.relation_tab, "关系网络")

        layout.addWidget(self.tabs, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setProperty("role", "primary")
        close_btn.clicked.connect(self.accept)
        bar.addWidget(close_btn)
        root_layout.addLayout(bar)

    def refresh(self):
        self.character_tab.refresh()
        self.location_tab.refresh()
        self.item_tab.refresh()
        self.org_tab.refresh()
        self.monster_tab.refresh()
        self.relation_tab.refresh()