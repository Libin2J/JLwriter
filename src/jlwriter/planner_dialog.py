"""
Planner 对话框：预设输入 + 分阶段独立页面 + 单阶段重写 + 接受写入
"""
import json

from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QComboBox, QSpinBox, QCheckBox, QPushButton,
    QMessageBox, QStackedWidget, QWidget, QListWidget, QListWidgetItem,
    QTextEdit
)
from PyQt5.QtCore import QTimer
from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ai_assistant import AIRequestThread
from .planner_agent import (
    PlannerPreset,
    PlannerSession,
    PLANNER_STAGES,
    build_stage_prompt,
    parse_stage_response,
    merge_planner_results_into_project,
)

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


# 文本类阶段：内容为单段文本
TEXT_STAGES = {
    "premise":      "premise",
    "background":   "story_background",
    "power_system": "power_system",
    "outline":      "outline",
}


class StagePage(QWidget):
    """单个阶段的编辑页面"""

    def __init__(self, stage, dialog):
        super().__init__()
        self.stage = stage
        self.dialog = dialog
        self._loading = False
        self._pending_revision = None
        self._check_thread = None
        self._fix_thread = None
        self._review_state = "idle"           # idle / reviewing / reviewed
        self._review_enabled_ext = False      # 外部传入的可用性

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # 标题 + 状态 + 重写按钮
        header = QHBoxLayout()
        title = QLabel(f"【{stage['label']}】{stage['description']}")
        title.setProperty("role", "subtitle")
        header.addWidget(title)

        self.status_label = QLabel("未生成")
        self.status_label.setProperty("role", "hint")
        header.addWidget(self.status_label)

        self.regenerate_btn = QPushButton("生成本阶段")
        self.regenerate_btn.clicked.connect(self._on_regenerate)
        self.regenerate_btn.setEnabled(True)  # 初始可点
        header.addWidget(self.regenerate_btn)
        layout.addLayout(header)

        self.review_btn = QPushButton("AI 审核本阶段")
        self.review_btn.clicked.connect(self._on_review)
        self.review_btn.setEnabled(False)
        header.addWidget(self.review_btn)

        # AI 思考（只读）
        layout.addWidget(QLabel("AI 思考："))
        self.thought_edit = QTextEdit()
        self.thought_edit.setReadOnly(True)
        self.thought_edit.setMaximumHeight(90)
        self.thought_edit.setPlaceholderText("（思考内容将在生成后显示）")
        layout.addWidget(self.thought_edit)

        # 内容（可编辑）
        layout.addWidget(QLabel("生成内容（可直接修改，接受时以当前内容为准）："))
        self.content_edit = QPlainTextEdit()
        self.content_edit.setPlaceholderText("（生成后显示）")
        layout.addWidget(self.content_edit, 1)

        self.resize(1000, 700)

    def _on_review(self):
        self.dialog.review_stage(self.stage["id"])

    def set_review_state(self, state: str):
        """只记录状态与文案，实际启用由 _apply_review_enabled 统一计算"""
        self._review_state = state
        text_map = {
            "idle": "AI 审核本阶段",
            "reviewing": "审核中...",
            "reviewed": "重新审核",
        }
        self.review_btn.setText(text_map.get(state, "AI 审核本阶段"))
        self._apply_review_enabled()

    def set_review_enabled(self, enabled: bool):
        """外部设置可用性，与内部状态合并"""
        self._review_enabled_ext = enabled
        self._apply_review_enabled()

    def _apply_review_enabled(self):
        # reviewing 状态强制禁用；否则以外部传入的可用性为准
        if self._review_state == "reviewing":
            self.review_btn.setEnabled(False)
        else:
            self.review_btn.setEnabled(self._review_enabled_ext)

    def set_content(self, parsed):
        self._loading = True
        thought = parsed.get("_thought", "")
        self.thought_edit.setPlainText(thought)

        sid = self.stage["id"]
        if sid in TEXT_STAGES:
            text = parsed.get(TEXT_STAGES[sid], "")
        else:
            data = {k: v for k, v in parsed.items() if not k.startswith("_")}
            text = json.dumps(data, ensure_ascii=False, indent=2)

        self.content_edit.setPlainText(text)
        self._loading = False

    def get_parsed_content(self):
        """把页面上的内容转为 merge 使用的 dict"""
        text = self.content_edit.toPlainText()
        thought = self.thought_edit.toPlainText()
        sid = self.stage["id"]

        if sid in TEXT_STAGES:
            return {"_thought": thought, TEXT_STAGES[sid]: text}

        # 列表类阶段：解析 JSON
        t = (text or "").strip()
        if not t:
            return {"_thought": thought}
        data = None
        try:
            data = json.loads(t)
        except json.JSONDecodeError:
            if HAS_JSON_REPAIR:
                data = json_repair.loads(t)
            else:
                raise ValueError("JSON 解析失败，请检查格式")
        if not isinstance(data, dict):
            raise ValueError("JSON 根节点必须是对象")
        data["_thought"] = thought
        return data

    def set_status(self, text, ok=True):
        from .ui.literary import repolish

        self.status_label.setText(text)
        self.status_label.setProperty("tone", "success" if ok else "danger")
        repolish(self.status_label)

    def set_actions_enabled(self, enabled: bool, generating: bool = False):
        """
        统一控制按钮可用性。
        - generating=True：本阶段正在生成，显示"生成中..."并禁用
        - generating=False：根据当前状态标签自动决定按钮文案
        """
        if generating:
            self.regenerate_btn.setEnabled(False)
            self.regenerate_btn.setText("生成中...")
            return

        # 文案：根据是否已完成决定
        label = self.status_label.text()
        if label.startswith("已完成"):
            self.regenerate_btn.setText("重新生成本阶段")
        else:
            self.regenerate_btn.setText("生成本阶段")
        self.regenerate_btn.setEnabled(enabled)

    # def set_review_enabled(self, enabled: bool):
    #     """独立控制审核按钮的可用性（文案由 set_review_state 决定）"""
    #     # 若处于"审核中"，强制禁用
    #     if self.review_btn.text() == "审核中...":
    #         self.review_btn.setEnabled(False)
    #         return
    #     self.review_btn.setEnabled(enabled)

    def _on_regenerate(self):
        # 判断下游是否有已完成阶段
        downstream_names = []
        order = [s["id"] for s in PLANNER_STAGES]
        try:
            idx = order.index(self.stage["id"])
        except ValueError:
            idx = -1
        if idx >= 0 and self.dialog.session:
            for s in PLANNER_STAGES[idx + 1:]:
                if s["id"] in self.dialog.session.completed_stages:
                    downstream_names.append(s["label"])

        has_content = bool(self.content_edit.toPlainText().strip())

        from .planner_regenerate_dialog import RegenerateStageDialog
        dlg = RegenerateStageDialog(
            stage_label=self.stage["label"],
            has_content=has_content,
            downstream_stages=downstream_names,
            parent=self.window(),
        )
        if dlg.exec_() != BaseDialog.Accepted:
            return

        mode, guidance = dlg.get_result()
        self.dialog.regenerate_stage(self.stage["id"], mode, guidance)


class PlannerDialog(BaseDialog):
    def __init__(self, project, ai_config, parent=None):
        self.project = project
        self.ai_config = ai_config
        self.session = None
        self._thread = None
        self._cancelled = False
        self._current_generating_stage = None
        self._auto_advance = True
        self._switching_programmatically = False
        self.stage_pages = {}
        self._review_thread = None
        self._current_review_stage = None
        self._pending_revision = None
        self._pipeline_stage = None
        self._pipeline_step = None
        self._check_thread = None
        self._fix_thread = None
        self._facts_thread = None

        super().__init__(
            parent,
            title="AI 策划",
            subtitle="从零构建世界观、故事框架与分卷结构",
            default_size=(1800, 1150),
            min_size=(900, 620),
            show_button_bar=False,
        )
        # 延迟检查项目是否已有设定，决定初始页面
        QTimer.singleShot(0, self._prompt_initial_choice)

    def build_content(self, layout):
        self.stack = QStackedWidget()
        self._setup_preset_page()
        self._setup_workspace_page()
        layout.addWidget(self.stack, 1)

    # ---------------- 预设页 ----------------
    def _setup_preset_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 16, 16, 16)

        # 顶部：提示 + 导入按钮
        head_row = QHBoxLayout()
        head_row.setSpacing(SPACING.sm)
        head_row.addWidget(QLabel(
            "请描述你想要的故事框架，策划 Agent 将基于以下预设从零构建完整的世界观与故事结构。"
        ))
        head_row.addStretch()

        self.save_preset_btn = QPushButton("💾 保存为预设")
        self.save_preset_btn.setToolTip(
            "将当前填写的设定保存为自定义预设，方便下次复用或反复生成（抽卡）"
        )
        self.save_preset_btn.clicked.connect(self._on_save_as_preset)
        head_row.addWidget(self.save_preset_btn)

        self.import_btn = QPushButton("📚 从预设导入")
        self.import_btn.setToolTip("打开预设书架，一键填入题材、主题、基调等选项")
        self.import_btn.clicked.connect(self._open_preset_browser)
        head_row.addWidget(self.import_btn)

        layout.addLayout(head_row)

        row = QHBoxLayout()
        row.addWidget(QLabel("题材:"))
        self.genre_edit = QLineEdit()
        self.genre_edit.setPlaceholderText("如：东方玄幻 / 硬科幻 / 悬疑推理 / 都市异能")
        row.addWidget(self.genre_edit)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("主题:"))
        self.theme_edit = QLineEdit()
        self.theme_edit.setPlaceholderText("如：复仇与救赎 / 成长 / 探索真理 / 家国天下")
        row.addWidget(self.theme_edit)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("基调:"))
        self.tone_edit = QLineEdit()
        self.tone_edit.setPlaceholderText("如：热血激昂 / 黑暗压抑 / 轻松幽默 / 史诗厚重")
        row.addWidget(self.tone_edit)
        layout.addLayout(row)

        row = QHBoxLayout()
        row.addWidget(QLabel("目标长度:"))
        self.length_combo = QComboBox()
        self.length_combo.addItems(["短篇", "中篇", "长篇", "超长篇"])
        self.length_combo.setCurrentText("长篇")
        row.addWidget(self.length_combo)

        row.addWidget(QLabel("分卷数:"))
        self.volume_spin = QSpinBox()
        self.volume_spin.setRange(1, 20)
        self.volume_spin.setValue(3)
        row.addWidget(self.volume_spin)
        row.addStretch()
        layout.addLayout(row)

        layout.addWidget(QLabel("需要生成的模块（勾选后 AI 会额外生成）："))
        self.need_power_check = QCheckBox("力量体系（修炼 / 魔法 / 科技等）")
        self.need_power_check.setChecked(True)
        layout.addWidget(self.need_power_check)
        self.need_org_check = QCheckBox("主要势力（门派 / 家族 / 王国 / 组织）")
        self.need_org_check.setChecked(True)
        layout.addWidget(self.need_org_check)
        self.need_loc_check = QCheckBox("地图与地点（大陆 / 城市 / 秘境）")
        self.need_loc_check.setChecked(True)
        layout.addWidget(self.need_loc_check)
        self.need_item_check = QCheckBox("重要物品（神器 / 法宝 / 道具）")
        layout.addWidget(self.need_item_check)
        self.need_monster_check = QCheckBox("怪物设计（妖兽 / 魔物 / 异种）")
        self.need_monster_check.setToolTip(
            "勾选后，策划流程会额外生成一份怪物档案，"
            "包含外形、行为与能力、纲目等信息。\n"
            "适合有战斗、探索、怪物生态设定的作品。"
        )
        layout.addWidget(self.need_monster_check)

        layout.addWidget(QLabel("补充说明（可选）："))
        self.notes_edit = QPlainTextEdit()
        self.notes_edit.setPlaceholderText(
            "如：希望主角是男性女性 / 节奏慢热、快速、超快 / 要求出现某种特定设定 / 需要避免某些元素..."
        )
        self.notes_edit.setMaximumHeight(680)
        layout.addWidget(self.notes_edit)

        layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        start_btn = QPushButton("开始生成")
        start_btn.clicked.connect(self._start_generation)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(start_btn)
        layout.addLayout(btn_row)

        self.stack.addWidget(page)

    # ---------------- 初始状态判断 ----------------

    def _has_existing_content(self) -> bool:
        if (self.project.premise or "").strip():
            return True
        if (self.project.story_background or "").strip():
            return True
        if (self.project.power_system or "").strip():
            return True
        if (self.project.outline or "").strip():
            return True
        if self.project.characters:
            return True
        if self.project.organizations:
            return True
        if self.project.locations:
            return True
        if self.project.items:
            return True
        if getattr(self.project, "monsters", None):
            return True
        return False

    def _build_existing_summary(self) -> dict:
        """生成现有内容的简短摘要，用于初始化对话框"""
        def _brief(text, max_len=40):
            text = (text or "").strip().replace("\n", " ")
            if len(text) > max_len:
                text = text[:max_len] + "…"
            return text

        return {
            "premise": _brief(self.project.premise),
            "background": _brief(self.project.story_background),
            "power_system": _brief(self.project.power_system),
            "outline": _brief(self.project.outline),
            "characters": (
                f"{len(self.project.characters)} 个角色"
                if self.project.characters else ""
            ),
            "organizations": (
                f"{len(self.project.organizations)} 个势力"
                if self.project.organizations else ""
            ),
            "locations": (
                f"{len(self.project.locations)} 个地点"
                if self.project.locations else ""
            ),
            "items": (
                f"{len(self.project.items)} 件物品"
                if self.project.items else ""
            ),
            "monsters": (
                f"{len(self.project.monsters)} 种怪物"
                if getattr(self.project, "monsters", None) else ""
            ),
        }

    def _prompt_initial_choice(self):
        """打开对话框时决定：载入已有设定 / 清空重来 / 取消"""
        if not self._has_existing_content():
            # 无已有内容，正常显示预设页
            return

        from .planner_init_choice_dialog import PlannerInitChoiceDialog
        dlg = PlannerInitChoiceDialog(
            self._build_existing_summary(), parent=self
        )
        if dlg.exec_() != BaseDialog.Accepted:
            self.reject()
            return

        choice = dlg.get_choice()
        if choice == "load":
            self._load_from_project()
        # choice == "fresh"：留在预设页，什么都不做

    # ---------------- 载入已有设定 ----------------

    def _infer_preset_from_project(self) -> PlannerPreset:
        """从 project 现有字段推导一个 preset（用户未重新填写时使用）"""
        return PlannerPreset(
            genre="",
            theme="",
            tone="",
            target_length="长篇",
            volume_count=max(len(self.project.volumes), 1),
            need_power_system=bool((self.project.power_system or "").strip()),
            need_organizations=bool(self.project.organizations),
            need_locations=bool(self.project.locations),
            need_items=bool(self.project.items),
            need_monsters=bool(getattr(self.project, "monsters", None)),  # 新增
            user_notes="",
        )

    def _collect_project_stage_data(self) -> dict:
        """把 project 现有内容组装成 stage_results 格式"""
        data = {}

        if (self.project.premise or "").strip():
            data["premise"] = {"premise": self.project.premise}

        if (self.project.story_background or "").strip():
            data["background"] = {
                "story_background": self.project.story_background
            }

        if (self.project.power_system or "").strip():
            data["power_system"] = {
                "power_system": self.project.power_system
            }

        if (self.project.outline or "").strip():
            data["outline"] = {"outline": self.project.outline}

        if self.project.characters:
            data["characters"] = {
                "characters": [c.to_dict() for c in self.project.characters]
            }

        if self.project.organizations:
            data["organizations"] = {
                "organizations": [
                    o.to_dict() for o in self.project.organizations
                ]
            }

        if self.project.locations:
            data["locations"] = {
                "locations": [l.to_dict() for l in self.project.locations]
            }

        if self.project.items:
            data["items"] = {
                "items": [i.to_dict() for i in self.project.items]
            }

        if getattr(self.project, "monsters", None):
            data["monsters"] = {
                "monsters": [m.to_dict() for m in self.project.monsters]
            }

        return data

    def _load_from_project(self):
        """把项目现有设定载入到工作区"""
        preset = self._infer_preset_from_project()
        self.session = PlannerSession(preset)
        self._cancelled = False
        self._auto_advance = False   # 载入后不自动推进

        stage_data = self._collect_project_stage_data()
        for sid, data in stage_data.items():
            if any(v for v in data.values() if v):
                self.session.mark_complete(sid, data)

        # 重建阶段页面
        self._rebuild_stage_pages()

        # 填充每个已完成阶段的内容
        for sid, data in stage_data.items():
            page = self.stage_pages.get(sid)
            if page and sid in self.session.completed_stages:
                page.set_content(data)
                page.set_status("已完成（已载入）", ok=True)

        # 切换到工作区
        self.stack.setCurrentIndex(1)
        self.accept_btn.setVisible(True)

        # 定位到第一个阶段
        stages = self.session.get_active_stages()
        if stages:
            self._switch_to_stage(stages[0]["id"])

        self._update_stage_list()
        self._update_auto_advance_hint()

    def _rebuild_stage_pages(self):
        """清空并重建 stage_list / stage_stack / stage_pages"""
        self.stage_list.blockSignals(True)
        self.stage_list.clear()
        while self.stage_stack.count() > 0:
            w = self.stage_stack.widget(0)
            self.stage_stack.removeWidget(w)
            w.deleteLater()
        self.stage_pages = {}

        for stage in self.session.get_active_stages():
            item = QListWidgetItem(f"○ {stage['label']}")
            self.stage_list.addItem(item)
            sp = StagePage(stage, self)
            self.stage_pages[stage["id"]] = sp
            self.stage_stack.addWidget(sp)
        self.stage_list.blockSignals(False)

    # ---------------- 工作区 ----------------
    def _setup_workspace_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(8, 8, 8, 8)

        top = QHBoxLayout()
        back_btn = QPushButton("← 返回预设")
        back_btn.clicked.connect(self._back_to_preset)     # 改为新方法
        top.addWidget(back_btn)

        self.auto_advance_btn = QPushButton("继续自动生成")
        self.auto_advance_btn.clicked.connect(self._resume_auto_advance)
        self.auto_advance_btn.setEnabled(False)
        top.addWidget(self.auto_advance_btn)

        self.progress_label = QLabel("0 / 0 完成")
        self.progress_label.setProperty("role", "hint")
        top.addWidget(self.progress_label)
        outer.addLayout(top)

        body = QHBoxLayout()

        self.stage_list = QListWidget()
        self.stage_list.setMaximumWidth(190)
        # 不再使用 currentRowChanged，避免程序化切换误触
        self.stage_list.itemClicked.connect(self._on_stage_clicked)
        body.addWidget(self.stage_list)

        self.stage_stack = QStackedWidget()
        body.addWidget(self.stage_stack, 1)

        outer.addLayout(body, 1)

        self.stack.addWidget(page)
        # 新增：初始化状态
        self._update_accept_button()

    def _back_to_preset(self):
        """返回预设页：隐藏 accept_btn，保留 session 供用户再次进入"""
        self.accept_btn.setVisible(False)
        self.stack.setCurrentIndex(0)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)
        bar.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self._cancel_generation)
        bar.addWidget(cancel_btn)

        self.accept_btn = QPushButton("接受并开始创作")
        self.accept_btn.setProperty("role", "primary")
        self.accept_btn.clicked.connect(self._accept_and_create)
        self.accept_btn.setEnabled(False)
        self.accept_btn.setVisible(False)  # 新增：初始隐藏
        self.accept_btn.setToolTip(
            "完成所有必填阶段（核心矛盾 / 故事背景 / 故事总纲 / 关键人物）后可用"
        )
        bar.addWidget(self.accept_btn)

        root_layout.addLayout(bar)

        # 新增：控件创建后立刻按当前 session 状态刷新一次
        self._update_accept_button()

    # ---------------- 预设书架 ---------------
    def _open_preset_browser(self):
        """打开预设书架，选中后填入各字段"""
        from .preset_browser_dialog import PresetBrowserDialog
        dlg = PresetBrowserDialog(self)
        if dlg.exec_() != BaseDialog.Accepted:
            return
        preset = dlg.get_selected()
        if not preset:
            return
        self._apply_preset(preset)

    def _apply_preset(self, preset):
        """把预设字段填入 UI（不覆盖用户已手填的字段，仅在预设非空时覆盖）"""
        if preset.get("genre"):
            self.genre_edit.setText(preset["genre"])
        if preset.get("theme"):
            self.theme_edit.setText(preset["theme"])
        if preset.get("tone"):
            self.tone_edit.setText(preset["tone"])

        length = preset.get("target_length", "")
        if length:
            idx = self.length_combo.findText(length)
            if idx >= 0:
                self.length_combo.setCurrentIndex(idx)

        vol = preset.get("volume_count", 0)
        if isinstance(vol, int) and vol > 0:
            self.volume_spin.setValue(vol)

        self.need_power_check.setChecked(
            bool(preset.get("need_power_system", False))
        )
        self.need_org_check.setChecked(
            bool(preset.get("need_organizations", False))
        )
        self.need_loc_check.setChecked(
            bool(preset.get("need_locations", False))
        )
        self.need_item_check.setChecked(
            bool(preset.get("need_items", False))
        )
        self.need_monster_check.setChecked(
            bool(preset.get("need_monsters", False))
        )

        notes = preset.get("user_notes", "")
        if notes:
            self.notes_edit.setPlainText(notes)

        QMessageBox.information(
            self, "导入成功",
            f"已导入预设「{preset.get('name', '')}」。\n"
            "所有字段均可继续修改，确认后点击「开始生成」。"
        )

    def _on_save_as_preset(self):
        """将当前填写的预设保存为自定义预设"""
        # 至少要有题材或补充说明，否则保存没意义
        genre = self.genre_edit.text().strip()
        notes = self.notes_edit.toPlainText().strip()
        if not genre and not notes:
            QMessageBox.information(
                self, "提示",
                "请至少填写「题材」或「补充说明」后再保存预设。"
            )
            return

        from .preset_browser_dialog import SavePresetDialog
        dlg = SavePresetDialog(default_name=genre, parent=self)
        if dlg.exec_() != BaseDialog.Accepted:
            return

        meta = dlg.get_result()
        if not meta:
            return

        # 组装完整预设
        preset = {
            "name": meta["name"],
            "icon": meta["icon"],
            "description": meta["description"],
            "genre": self.genre_edit.text().strip(),
            "theme": self.theme_edit.text().strip(),
            "tone": self.tone_edit.text().strip(),
            "target_length": self.length_combo.currentText(),
            "volume_count": self.volume_spin.value(),
            "need_power_system": self.need_power_check.isChecked(),
            "need_organizations": self.need_org_check.isChecked(),
            "need_locations": self.need_loc_check.isChecked(),
            "need_items": self.need_item_check.isChecked(),
            "need_monsters": self.need_monster_check.isChecked(),  # 新增
            "user_notes": notes,
        }

        from .preset_loader import save_user_preset
        ok = save_user_preset(preset)

        if ok:
            QMessageBox.information(
                self, "已保存",
                f"预设「{meta['name']}」已保存。\n\n"
                "下次可通过「📚 从预设导入」快速加载。"
            )
        else:
            QMessageBox.warning(
                self, "保存失败",
                "写入预设文件失败，请检查磁盘权限或配置目录。"
            )

    # ---------------- 继续重新生成 -------------
    def _resume_auto_advance(self):
        """用户点击后恢复自动推进"""
        # 双重保险：若流水线或生成线程仍在运行，拒绝响应
        if self._pipeline_stage is not None:
            QMessageBox.information(
                self, "提示", "当前阶段仍在处理中，请稍候。"
            )
            return
        if self._thread and self._thread.isRunning():
            QMessageBox.information(
                self, "提示", "正在生成阶段，请稍候。"
            )
            return
        if not self.session:
            return

        self._auto_advance = True
        self._update_auto_advance_hint()

        # 优先处理失败阶段
        if self.session.failed_stages:
            failed = self.session.failed_stages[0]
            self._switch_to_stage(failed)
            self._generate_stage(failed)
            return

        nxt = self.session.next_stage()
        if nxt:
            self._switch_to_stage(nxt["id"])
            self._generate_stage(nxt["id"])
        else:
            self._update_accept_button()

    def _update_auto_advance_hint(self):
        if not self.session:
            self.auto_advance_btn.setEnabled(False)
            self.auto_advance_btn.setText("等待开始")
            self._update_all_stage_buttons()
            return

        # 流水线运行中
        if self._pipeline_stage is not None:
            step_text = {
                "check": "校验中...",
                "fix": "修正中...",
                "facts": "提炼关键事实...",
            }.get(self._pipeline_step, "处理中...")
            self.auto_advance_btn.setEnabled(False)
            self.auto_advance_btn.setText(step_text)
            self._update_all_stage_buttons()
            return

        # 生成中：以 _current_generating_stage 为准（不受 isRunning 时序影响）
        if (self._current_generating_stage is not None
                or (self._thread and self._thread.isRunning())):
            self.auto_advance_btn.setEnabled(False)
            self.auto_advance_btn.setText("生成中...")
            self._update_all_stage_buttons()
            return

        all_done = (
                self.session.next_stage() is None
                and not self.session.failed_stages
        )
        if all_done:
            self.auto_advance_btn.setEnabled(False)
            self.auto_advance_btn.setText("全部完成")
            self._update_all_stage_buttons()
            return

        if self._auto_advance:
            self.auto_advance_btn.setEnabled(False)
            self.auto_advance_btn.setText("自动生成中...")
            self._update_all_stage_buttons()
            return

        self.auto_advance_btn.setEnabled(True)
        self.auto_advance_btn.setText("继续自动生成")
        self._update_all_stage_buttons()

    def _update_all_stage_buttons(self):
        """统一仲裁所有阶段的按钮可用性"""
        if not getattr(self, "stage_pages", None):
            return

        # 任何任务占用时，全局禁用
        busy = (
            (self._pipeline_stage is not None)
            or (self._current_generating_stage is not None)  # 新增
            or (self._thread and self._thread.isRunning())
            or (self._review_thread and self._review_thread.isRunning())
        )

        completed = set(self.session.completed_stages) if self.session else set()
        failed = set(self.session.failed_stages) if self.session else set()

        for sid, page in self.stage_pages.items():
            is_generating = (sid == self._current_generating_stage)

            if is_generating:
                page.set_actions_enabled(False, generating=True)
                page.set_review_enabled(False)
                continue

            # 生成按钮：空闲时启用
            page.set_actions_enabled(not busy, generating=False)

            # 审核按钮：空闲 + 已完成 + 未失败
            review_ok = (
                not busy
                and sid in completed
                and sid not in failed
            )
            page.set_review_enabled(review_ok)

    # ---------------- 生成流程 ----------------
    def _start_generation(self):
        preset = PlannerPreset(
            genre=self.genre_edit.text().strip(),
            theme=self.theme_edit.text().strip(),
            tone=self.tone_edit.text().strip(),
            target_length=self.length_combo.currentText(),
            volume_count=self.volume_spin.value(),
            need_power_system=self.need_power_check.isChecked(),
            need_organizations=self.need_org_check.isChecked(),
            need_locations=self.need_loc_check.isChecked(),
            need_items=self.need_item_check.isChecked(),
            need_monsters=self.need_monster_check.isChecked(),  # 新增
            user_notes=self.notes_edit.toPlainText().strip(),
        )
        self.session = PlannerSession(preset)
        self._cancelled = False
        self._auto_advance = True

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            self.session = None
            return

        # 使用抽出的方法重建页面
        self._rebuild_stage_pages()

        self.stack.setCurrentIndex(1)
        self.accept_btn.setVisible(True)

        first_stage = self.session.next_stage()
        if first_stage:
            self._switch_to_stage(first_stage["id"])
            self._generate_stage(first_stage["id"])

        self._update_auto_advance_hint()

    def _switch_to_stage(self, stage_id):
        """程序化切换：只改变显示，不影响 _auto_advance"""
        stages = self.session.get_active_stages()
        for i, s in enumerate(stages):
            if s["id"] == stage_id:
                # 阻断信号，避免触发用户点击处理
                self.stage_list.blockSignals(True)
                self.stage_list.setCurrentRow(i)
                self.stage_list.blockSignals(False)
                self.stage_stack.setCurrentIndex(i)
                return

    def _on_stage_clicked(self, item):
        row = self.stage_list.row(item)
        if row < 0:
            return
        self.stage_stack.setCurrentIndex(row)
        # 用户主动切换时若流水线在跑，不让按钮状态误变
        if self._pipeline_stage is None:
            self._auto_advance = False
        self._update_auto_advance_hint()

    def _generate_stage(self, stage_id):
        if self._cancelled:
            return
        if self._pipeline_stage and self._pipeline_stage != stage_id:
            QMessageBox.information(
                self, "提示",
                f"阶段【{self._pipeline_stage}】正在校验中，请稍候。"
            )
            return
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前阶段生成完成。")
            return

        stage = next(
            (s for s in self.session.get_active_stages() if s["id"] == stage_id),
            None
        )
        if not stage:
            return

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        self._current_generating_stage = stage_id
        page = self.stage_pages[stage_id]
        page.set_status("生成中...", ok=True)
        self._update_stage_list()
        self._update_auto_advance_hint()  # 新增：立即禁用按钮

        prompt = build_stage_prompt(
            self.session, stage,
            enable_golden_three=getattr(
                self.ai_config, "enable_golden_three_chapters", False
            ),
        )
        self._thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*10, json_mode=True, timeout=300,
        )
        self._thread.finished.connect(
            lambda text, sid=stage_id: self._on_stage_finished(sid, text)
        )
        self._thread.error.connect(
            lambda err, sid=stage_id: self._on_stage_error(sid, err)
        )
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def regenerate_stage(self, stage_id, mode="fresh", guidance=""):
        """
        重新生成某阶段。
        mode="fresh"：完全重新生成（清除当前 + 下游）
        mode="optimize"：基于现有内容优化（不动下游）
        """
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前阶段生成完成。")
            return
        if self._pipeline_stage is not None:
            QMessageBox.information(
                self, "提示",
                f"阶段【{self._stage_label(self._pipeline_stage)}】"
                f"正在校验中，请稍候。"
            )
            return
        if self._review_thread and self._review_thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前审核完成。")
            return

        if mode == "optimize":
            self._generate_stage_optimize(stage_id, guidance)
            return

        # ===== mode == "fresh"：原有逻辑 =====
        order = [s["id"] for s in PLANNER_STAGES]
        try:
            idx = order.index(stage_id)
        except ValueError:
            return

        active = [s["id"] for s in self.session.get_active_stages()]
        downstream = [s for s in order[idx + 1:] if s in active]
        affected = [s for s in downstream if s in self.session.completed_stages]

        if affected:
            labels = "、".join(self._stage_label(s) for s in affected)
            reply = QMessageBox.question(
                self, "确认重新生成",
                f"重新生成【{self._stage_label(stage_id)}】会使其后阶段失效：\n"
                f"{labels}\n\n"
                "这些阶段将被清除并随流水线重新生成。是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        for sid in reversed(downstream):
            self._clear_stage_state(sid)
        self._clear_stage_state(stage_id)

        self._auto_advance = True
        self._switch_to_stage(stage_id)
        self._generate_stage(stage_id)

    def _generate_stage_optimize(self, stage_id, guidance):
        """基于现有内容优化某阶段（不动下游，不自动推进）"""
        if self._cancelled:
            return
        if self._pipeline_stage is not None:
            QMessageBox.information(
                self, "提示", "当前有其他阶段正在校验，请稍候。"
            )
            return
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前阶段生成完成。")
            return

        page = self.stage_pages.get(stage_id)
        if not page:
            return

        current_content = page.content_edit.toPlainText().strip()
        if not current_content:
            QMessageBox.information(
                self, "提示",
                "当前阶段内容为空，无法优化；请选择完全重新生成。"
            )
            return

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        stage = next(
            (s for s in self.session.get_active_stages()
             if s["id"] == stage_id),
            None
        )
        if not stage:
            return

        from .planner_agent import build_stage_optimize_prompt
        prompt = build_stage_optimize_prompt(
            self.session, stage, current_content, guidance,
            enable_golden_three=getattr(
                self.ai_config, "enable_golden_three_chapters", False
            ),
        )

        self._current_generating_stage = stage_id
        page.set_status("优化中...", ok=True)
        self._update_stage_list()
        self._update_auto_advance_hint()

        self._thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192 * 10, json_mode=True, timeout=300,
        )
        self._thread.finished.connect(
            lambda text, sid=stage_id:
            self._on_stage_optimize_finished(sid, text)
        )
        self._thread.error.connect(
            lambda err, sid=stage_id:
            self._on_stage_optimize_error(sid, err)
        )
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_stage_optimize_finished(self, stage_id, text):
        self._thread = None
        self._current_generating_stage = None
        if self._cancelled:
            return

        page = self.stage_pages.get(stage_id)
        if not page:
            return

        try:
            parsed = parse_stage_response(text)
        except Exception as e:
            page.set_status("优化失败：解析失败", ok=False)
            self._update_stage_list()
            QMessageBox.warning(
                self, "解析失败",
                f"优化结果解析失败：{e}\n"
                "当前内容保持不变，可重新尝试。"
            )
            return

        # 更新内容，但不进入流水线
        page.set_content(parsed)
        self.session.stage_results[stage_id] = parsed
        if stage_id not in self.session.completed_stages:
            self.session.completed_stages.append(stage_id)
        page.set_status("已完成 √ 已优化", ok=True)

        self._update_stage_list()
        self._update_accept_button()

        QMessageBox.information(
            self, "优化完成",
            f"阶段【{page.stage['label']}】已优化。\n"
            "下游阶段未受影响；如需连锁更新，可手动重新生成下游。"
        )

    def _on_stage_optimize_error(self, stage_id, err):
        self._thread = None
        self._current_generating_stage = None
        if self._cancelled:
            return
        page = self.stage_pages.get(stage_id)
        if page:
            page.set_status("优化失败", ok=False)
        self._update_stage_list()
        self._update_auto_advance_hint()
        QMessageBox.warning(self, "优化失败", err)

    def _clear_stage_state(self, stage_id):
        """清除某阶段的全部状态与 UI"""
        if stage_id in self.session.completed_stages:
            self.session.completed_stages.remove(stage_id)
        if stage_id in self.session.failed_stages:
            self.session.failed_stages.remove(stage_id)
        if stage_id in self.session.stage_results:
            del self.session.stage_results[stage_id]
        if stage_id in self.session.key_facts_registry:
            del self.session.key_facts_registry[stage_id]

        page = self.stage_pages.get(stage_id)
        if page:
            page.set_status("未生成", ok=False)
            page.thought_edit.clear()
            page.content_edit.clear()
            page.set_review_state("idle")
            page.set_review_enabled(False)
            page.set_actions_enabled(True)

    def _stage_label(self, stage_id):
        for s in PLANNER_STAGES:
            if s["id"] == stage_id:
                return s["label"]
        return stage_id

    def _on_stage_finished(self, stage_id, text):
        self._thread = None
        self._current_generating_stage = None
        if self._cancelled:
            return

        page = self.stage_pages.get(stage_id)
        if not page:
            return

        try:
            parsed = parse_stage_response(text)
        except Exception as e:
            self.session.mark_failed(stage_id)
            page.set_status("解析失败", ok=False)
            self._update_stage_list()
            QMessageBox.warning(
                self, "解析失败",
                f"阶段【{page.stage['label']}】解析失败：{e}\n"
                "可点击「重新生成本阶段」重试，或点击左侧其他阶段。"
            )
            return

        page.set_content(parsed)
        self.session.mark_complete(stage_id, parsed)
        self._update_stage_list()
        self._update_accept_button()

        # 进入校验流水线（不再直接推进）
        self._run_pipeline(stage_id)

    def _run_pipeline(self, stage_id):
        """启动或恢复某阶段的校验流水线"""
        self._pipeline_stage = stage_id
        self._update_auto_advance_hint()  # 新增：进入流水线立刻刷新按钮
        page = self.stage_pages.get(stage_id)
        if not page:
            self._pipeline_stage = None
            self._update_auto_advance_hint()  # 新增：进入流水线立刻刷新按钮
            return

        # Step 1：决定是否需要校验
        if self._has_prior_stages(stage_id):
            self._pipeline_step = "check"
            page.set_status("校验中...", ok=True)
            self._update_auto_advance_hint()  # 新增：进入流水线立刻刷新按钮
            self._start_layer1_check(stage_id)
        else:
            # 第一阶段无需校验
            self._pipeline_step = "facts"
            page.set_status("提炼关键事实...", ok=True)
            self._update_auto_advance_hint()  # 新增：进入流水线立刻刷新按钮
            self._extract_key_facts(stage_id)

    def _has_prior_stages(self, stage_id):
        """检查当前阶段之前是否有已完成的阶段"""
        order = [s["id"] for s in PLANNER_STAGES]
        try:
            idx = order.index(stage_id)
        except ValueError:
            return False
        for s in PLANNER_STAGES[:idx]:
            if s["id"] in self.session.completed_stages:
                return True
        return False

    def _start_layer1_check(self, stage_id):
        from .planner_agent import build_consistency_check_prompt

        if self._pipeline_stage != stage_id:
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            # 无审核 agent，直接跳过校验进入 facts
            self._pipeline_step = "facts"
            self._extract_key_facts(stage_id)
            return

        registry = {
            sid: facts for sid, facts in self.session.key_facts_registry.items()
            if sid != stage_id
        }

        parsed = self.session.stage_results[stage_id]
        stage = next(s for s in PLANNER_STAGES if s["id"] == stage_id)
        prompt = build_consistency_check_prompt(
            stage_id, stage["label"], parsed, registry
        )

        self._check_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*6, json_mode=True, timeout=180,
        )
        self._check_thread.finished.connect(
            lambda text, sid=stage_id, reg=registry:
            self._on_layer1_finished(sid, text, reg)
        )
        self._check_thread.error.connect(
            lambda err, sid=stage_id: self._on_layer1_error(sid, err)
        )
        self._check_thread.finished.connect(self._check_thread.deleteLater)
        self._check_thread.start()

    def _on_layer1_finished(self, stage_id, text, registry):
        self._check_thread = None

        if self._pipeline_stage != stage_id:
            return

        page = self.stage_pages.get(stage_id)
        if not page:
            self._pipeline_stage = None
            self._update_auto_advance_hint()
            return

        from .planner_agent import parse_consistency_check_response
        try:
            report = parse_consistency_check_response(text)
        except Exception:
            page.set_status("已完成（校验失败）", ok=False)
            self._pipeline_step = "facts"
            self._update_auto_advance_hint()  # 新增
            self._extract_key_facts(stage_id)
            return

        issues = report.get("issues", [])
        high = [it for it in issues if it["severity"] == "high"]
        medium = [it for it in issues if it["severity"] == "medium"]

        if not issues:
            page.set_status(
                f"已完成 √ 一致 ({report['overall_score']})", ok=True
            )
            self._pipeline_step = "facts"
            self._update_auto_advance_hint()  # 新增
            self._extract_key_facts(stage_id)
            return

        if high:
            page.set_status(
                f"校验发现 {len(high)} 个高严重问题，正在修正...", ok=False
            )
            self._pipeline_step = "fix"
            self._update_auto_advance_hint()  # 新增
            self._start_auto_fix(stage_id, high, registry)
            return

        # 中低风险：同步弹窗前先禁用按钮，避免弹窗期间按钮残留可点状态
        page.set_status(
            f"已完成 √ 一致评分 {report['overall_score']}", ok=True
        )
        self.auto_advance_btn.setEnabled(False)
        self.auto_advance_btn.setText("等待用户确认...")  # 新增

        from .review_report_dialog import ReviewReportDialog
        dlg = ReviewReportDialog(report, parent=self)
        dlg.exec_()

        if self._pipeline_stage != stage_id:
            return

        if dlg.request_revision():
            selected = dlg.get_selected_issues()
            if selected:
                self._pipeline_step = "fix"
                self._update_auto_advance_hint()  # 新增
                self._start_auto_fix(stage_id, selected, registry)
                return

        self._pipeline_step = "facts"
        self._update_auto_advance_hint()  # 新增
        self._extract_key_facts(stage_id)

    def _on_layer1_error(self, stage_id, err):
        self._check_thread = None
        page = self.stage_pages.get(stage_id)
        if page:
            page.set_status("已完成（校验失败）", ok=False)
        # 校验失败不阻断流程
        self._after_pipeline(stage_id)

    def _start_auto_fix(self, stage_id, issues, registry):
        from .planner_agent import build_consistency_fix_prompt

        if self._pipeline_stage != stage_id:
            return

        # 优先使用 reviewer（更快、更便宜），未配置时降级到 planner
        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            resolved = self.ai_config.resolve_agent("planner")

        if not resolved or not resolved.api_key:
            # 两个 agent 都不可用 → 跳过修正，直接 facts
            self._pipeline_step = "facts"
            self._update_auto_advance_hint()
            self._extract_key_facts(stage_id)
            return

        stage = next(s for s in PLANNER_STAGES if s["id"] == stage_id)
        parsed = self.session.stage_results[stage_id]
        prompt = build_consistency_fix_prompt(
            stage_id, stage["label"], parsed, issues, registry
        )

        self._update_auto_advance_hint()
        self._fix_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*4, json_mode=True, timeout=180,
        )
        self._fix_thread.finished.connect(
            lambda text, sid=stage_id: self._on_auto_fix_finished(sid, text)
        )
        self._fix_thread.error.connect(
            lambda err, sid=stage_id: self._on_auto_fix_error(sid, err)
        )
        self._fix_thread.finished.connect(self._fix_thread.deleteLater)
        self._fix_thread.start()

    def _on_auto_fix_finished(self, stage_id, text):
        self._fix_thread = None

        if self._pipeline_stage != stage_id:
            return

        page = self.stage_pages.get(stage_id)
        if not page:
            self._pipeline_stage = None
            self._update_auto_advance_hint()
            return

        from .reviewer_agent import parse_patch_response, apply_stage_patches
        try:
            patches = parse_patch_response(text)
            parsed = self.session.stage_results[stage_id]
            result = apply_stage_patches(parsed, patches, stage_id)
        except Exception:
            page.set_status("已完成（修正解析失败）", ok=False)
            self._pipeline_step = "facts"
            self._update_auto_advance_hint()  # 新增
            self._extract_key_facts(stage_id)
            return

        if result["applied"] > 0:
            self.session.stage_results[stage_id] = result["data"]
            page.set_content(result["data"])
            page.set_status(
                f"已完成 √ 已自动修正 {result['applied']} 处", ok=True
            )
        else:
            page.set_status("已完成（修正无效果）", ok=False)

        self._pipeline_step = "facts"
        self._update_auto_advance_hint()  # 新增
        self._extract_key_facts(stage_id)

    def _on_auto_fix_error(self, stage_id, err):
        self._fix_thread = None
        if self._pipeline_stage != stage_id:
            return
        page = self.stage_pages.get(stage_id)
        if page:
            page.set_status("已完成（修正失败）", ok=False)
        self._pipeline_step = "facts"
        self._update_auto_advance_hint()  # 新增
        self._extract_key_facts(stage_id)

    def _after_pipeline(self, stage_id):
        if self._pipeline_stage != stage_id:
            return

        self._pipeline_stage = None
        self._pipeline_step = None
        self._update_auto_advance_hint()

        self._update_stage_list()
        self._update_accept_button()  # ← 确保存在

        if self._auto_advance:
            nxt = self.session.next_stage()
            if nxt:
                self._switch_to_stage(nxt["id"])
                self._generate_stage(nxt["id"])
            else:
                self._auto_advance = False
                self._update_auto_advance_hint()
                self._update_accept_button()  # ← 最后一个阶段也刷新
        else:
            self._update_auto_advance_hint()
            self._update_accept_button()

    def _extract_key_facts(self, stage_id):
        """提炼当前阶段的关键事实"""
        from .key_facts import (
            build_key_facts_extraction_prompt,
            extract_key_facts,
        )

        if self._pipeline_stage != stage_id:
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            parsed = self.session.stage_results.get(stage_id, {})
            self.session.key_facts_registry[stage_id] = extract_key_facts(
                stage_id, parsed
            )
            self._after_pipeline(stage_id)
            return

        stage = next(s for s in PLANNER_STAGES if s["id"] == stage_id)
        parsed = self.session.stage_results.get(stage_id, {})
        prompt = build_key_facts_extraction_prompt(
            stage_id, stage["label"], parsed
        )

        self._update_auto_advance_hint()  # 新增：确保显示"提炼关键事实..."
        self._facts_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192, json_mode=True, timeout=60,
        )
        self._facts_thread.finished.connect(
            lambda text, sid=stage_id: self._on_facts_extracted(sid, text)
        )
        self._facts_thread.error.connect(
            lambda err, sid=stage_id: self._on_facts_error(sid, err)
        )
        self._facts_thread.finished.connect(self._facts_thread.deleteLater)
        self._facts_thread.start()

    def _on_facts_extracted(self, stage_id, text):
        self._facts_thread = None
        if self._pipeline_stage != stage_id:
            return

        from .key_facts import parse_key_facts_response, extract_key_facts
        parsed = self.session.stage_results.get(stage_id, {})
        try:
            facts = parse_key_facts_response(text)
            if not facts:
                facts = extract_key_facts(stage_id, parsed)
        except Exception:
            facts = extract_key_facts(stage_id, parsed)

        self.session.key_facts_registry[stage_id] = facts
        self._after_pipeline(stage_id)

    def _on_facts_error(self, stage_id, err):
        self._facts_thread = None
        if self._pipeline_stage != stage_id:
            return

        from .key_facts import extract_key_facts
        parsed = self.session.stage_results.get(stage_id, {})
        self.session.key_facts_registry[stage_id] = extract_key_facts(
            stage_id, parsed
        )
        self._after_pipeline(stage_id)


    def _on_stage_error(self, stage_id, err):
        self._thread = None
        self._current_generating_stage = None
        if self._cancelled:
            return
        if self._pipeline_stage == stage_id:
            self._pipeline_stage = None
            self._pipeline_step = None

        page = self.stage_pages.get(stage_id)
        if not page:
            self._update_auto_advance_hint()  # 新增：清空状态后刷新
            return

        self.session.mark_failed(stage_id)
        page.set_status("失败", ok=False)
        self._update_stage_list()
        self._update_auto_advance_hint()

        if "被截断" in err or "max_tokens" in err:
            QMessageBox.warning(
                self, "输出截断",
                f"阶段【{page.stage['label']}】输出过长被截断。\n"
                "可点击「重新生成本阶段」重试。"
            )
        else:
            QMessageBox.warning(
                self, "AI 错误",
                f"阶段【{page.stage['label']}】出错：{err}"
            )

    def _update_stage_list(self):
        stages = self.session.get_active_stages()
        for i, s in enumerate(stages):
            sid = s["id"]
            if sid in self.session.completed_stages:
                icon = "●"
            elif sid in self.session.failed_stages:
                icon = "×"
            elif sid == self._current_generating_stage:
                icon = "◎"
            else:
                icon = "○"
            item = self.stage_list.item(i)
            if item:
                item.setText(f"{icon} {s['label']}")
        done = len(self.session.completed_stages)
        total = len(stages)
        self.progress_label.setText(f"{done} / {total} 完成")
        self._update_auto_advance_hint()
        self._update_accept_button()  # 新增兜底

    def _update_accept_button(self):
        if not hasattr(self, "accept_btn") or self.accept_btn is None:
            return
        if not self.session:
            self.accept_btn.setEnabled(False)
            return

        required_ids = ["premise", "background", "outline", "characters"]
        try:
            active_ids = [s["id"] for s in self.session.get_active_stages()]
            completed = set(self.session.completed_stages)
        except Exception:
            self.accept_btn.setEnabled(False)
            return

        pending = [
            sid for sid in required_ids
            if sid in active_ids and sid not in completed
        ]

        all_done = not pending
        self.accept_btn.setEnabled(all_done)

        # 辅助提示
        if hasattr(self, "accept_btn") and not all_done:
            labels = "、".join(
                self._stage_label(sid) for sid in pending
            )
            self.accept_btn.setToolTip(f"还需完成：{labels}")
        else:
            self.accept_btn.setToolTip("")

    # ---------------- 接受 ----------------
    def _accept_and_create(self):
        if not self.session:
            return

        # 收集各页面上的最新内容
        for sid, page in self.stage_pages.items():
            if sid not in self.session.completed_stages:
                continue
            try:
                parsed = page.get_parsed_content()
                self.session.stage_results[sid] = parsed
            except Exception as e:
                QMessageBox.warning(
                    self, "解析失败",
                    f"阶段【{page.stage['label']}】内容无法解析：{e}\n"
                    "请修正 JSON 格式后重试。"
                )
                self._switch_to_stage(sid)
                return

        try:
            self._merge_stats = merge_planner_results_into_project(
                self.project, self.session
            )
        except Exception as e:
            QMessageBox.critical(self, "写入失败", str(e))
            return

        self.accept()

    def get_merge_stats(self):
        return getattr(self, "_merge_stats", None)

    def _cancel_generation(self):
        self._cancelled = True
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        self.reject()

    def get_session(self):
        return self.session

    # --------------- 审核各阶段 -------------
    def review_stage(self, stage_id):
        """审核单个阶段"""
        if self._review_thread and self._review_thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前审核完成。")
            return
            # 若流水线正在该阶段上跑，提示等待
        if self._pipeline_stage == stage_id:
            QMessageBox.information(
                self, "提示",
                "本阶段正在自动校验中，请稍候再手动审核。"
            )
            return
        if stage_id not in self.session.stage_results:
            QMessageBox.information(self, "提示", "本阶段尚未生成内容。")
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "审核 Agent 未配置 API Key。")
            return

        stage = next(s for s in PLANNER_STAGES if s["id"] == stage_id)
        parsed = self.session.stage_results[stage_id]
        preset_text = self._build_preset_text()
        prior = self._build_prior_context_before(stage_id)

        from .reviewer_agent import build_planner_stage_review_prompt
        prompt = build_planner_stage_review_prompt(
            stage_id, stage["label"], parsed, preset_text, prior
        )

        self._current_review_stage = stage_id
        self.stage_pages[stage_id].set_review_state("reviewing")
        self._update_auto_advance_hint()  # 新增：刷新按钮，让本阶段审核按钮显示"审核中..."

        self._review_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*10, json_mode=True, timeout=180,
        )
        self._review_thread.finished.connect(
            lambda text, sid=stage_id: self._on_stage_review_finished(sid, text)
        )
        self._review_thread.error.connect(
            lambda err, sid=stage_id: self._on_stage_review_error(sid, err)
        )
        self._review_thread.finished.connect(self._review_thread.deleteLater)
        self._review_thread.start()

    def _on_stage_review_finished(self, stage_id, text):
        self._review_thread = None
        self.stage_pages[stage_id].set_review_state("idle")

        from .reviewer_agent import parse_review_response
        try:
            report = parse_review_response(text)
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"审核结果解析失败：{e}")
            return

        from .review_report_dialog import ReviewReportDialog
        dlg = ReviewReportDialog(report, parent=self)
        dlg.exec_()

        if not dlg.request_revision():
            return

        selected_issues = dlg.get_selected_issues()
        if not selected_issues:
            return

        # 发起修订请求
        self._request_stage_revision(stage_id, selected_issues)
        self._update_auto_advance_hint()  # 新增：刷新按钮，让本阶段审核按钮显示"审核中..."

    def _request_stage_revision(self, stage_id, issues):
        if self._review_thread and self._review_thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前任务完成。")
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "审核 Agent 未配置 API Key。")
            return

        stage = next(s for s in PLANNER_STAGES if s["id"] == stage_id)
        parsed = self.session.stage_results.get(stage_id, {})

        from .reviewer_agent import (
            build_planner_stage_revision_prompt,
            parse_patch_response,
            apply_stage_patches,
        )
        prompt = build_planner_stage_revision_prompt(
            stage_id, stage["label"], parsed, issues
        )

        self._pending_revision = (stage_id, parsed)
        self.stage_pages[stage_id].set_review_state("reviewing")

        self._review_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*8, json_mode=True, timeout=300,
        )
        self._review_thread.finished.connect(self._on_revision_finished)
        self._review_thread.error.connect(self._on_revision_error)
        self._review_thread.finished.connect(self._review_thread.deleteLater)
        self._review_thread.start()

    def _on_revision_finished(self, text):
        self._review_thread = None
        if not self._pending_revision:
            return
        stage_id, parsed = self._pending_revision
        self._pending_revision = None
        self.stage_pages[stage_id].set_review_state("idle")

        from .reviewer_agent import parse_patch_response, apply_stage_patches
        try:
            patches = parse_patch_response(text)
            result = apply_stage_patches(parsed, patches, stage_id)
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"修订方案解析失败：{e}")
            return

        applied = result["applied"]
        skipped = result["skipped"]
        if applied == 0:
            QMessageBox.information(
                self, "无修订",
                f"AI 未生成有效修订（跳过 {skipped} 条）。"
            )
            return

        # 更新 session 与页面
        self.session.stage_results[stage_id] = result["data"]
        self.stage_pages[stage_id].set_content(result["data"])
        QMessageBox.information(
            self, "已应用",
            f"修订已应用：{applied} 条生效，{skipped} 条跳过。\n"
            "可在页面中继续手动调整。"
        )

    def _on_revision_error(self, err):
        self._review_thread = None
        self._pending_revision = None
        QMessageBox.warning(self, "修订失败", err)

    def _on_stage_review_error(self, stage_id, err):
        self._review_thread = None
        self.stage_pages[stage_id].set_review_state("idle")
        QMessageBox.warning(self, "审核失败", err)
        self._update_auto_advance_hint()  # 新增：刷新按钮，让本阶段审核按钮显示"审核中..."

    def _build_preset_text(self):
        preset = self.session.preset
        lines = []
        if preset.genre:
            lines.append(f"题材：{preset.genre}")
        if preset.theme:
            lines.append(f"主题：{preset.theme}")
        if preset.tone:
            lines.append(f"基调：{preset.tone}")
        if preset.target_length:
            lines.append(f"目标长度：{preset.target_length}")
        if preset.volume_count:
            lines.append(f"分卷数：{preset.volume_count}")
        return "\n".join(lines)

    def _build_prior_context_before(self, stage_id):
        """已生成阶段在本阶段之前的摘要"""
        order = [s["id"] for s in PLANNER_STAGES]
        try:
            idx = order.index(stage_id)
        except ValueError:
            return ""
        parts = []
        for s in PLANNER_STAGES[:idx]:
            sid = s["id"]
            if sid in self.session.stage_results:
                parts.append(f"【{s['label']}】")
                parts.append(self._format_brief(self.session.stage_results[sid]))
        return "\n".join(parts)

    def _format_brief(self, parsed):
        if isinstance(parsed, dict):
            lines = []
            for k, v in parsed.items():
                if k.startswith("_"):
                    continue
                if isinstance(v, list):
                    lines.append(f"{k}: {len(v)} 项")
                else:
                    lines.append(f"{k}: {str(v)[:200]}")
            return "\n".join(lines)
        return str(parsed)[:500]