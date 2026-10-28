"""
章节规划对话框：卷 → 弧 → 章 三层结构，支持批次生成
"""
import copy
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QMessageBox, QSplitter, QWidget, QPlainTextEdit, QSpinBox,
    QLineEdit, QFormLayout, QScrollArea, QTreeWidget, QTreeWidgetItem,
    QInputDialog, QStackedWidget, QComboBox
)
from PyQt5.QtCore import Qt

from .ai_assistant import AIRequestThread
from .planner_agent import (
    build_volume_extraction_prompt,
    parse_volume_response,
    build_arc_planning_prompt,
    parse_arc_response,
    build_arc_chapters_prompt,
    parse_chapter_plan_response,
)
from .models import Volume, Chapter, ChapterPlan, StoryArc, StoryProject
from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ui.widgets.section import HintBox
from .planner_regenerate_dialog import RegenerateStageDialog


BATCH_SIZE = 16
CHAPTER_PREFERENCES = [
    "日常", "战斗", "抒情", "紧张", "悬疑", "恐怖",
    "热血", "温情", "压抑", "幽默", "史诗", "过渡",
]

class ChapterPlannerDialog(BaseDialog):
    def __init__(self, project, ai_config, parent=None,
                 focus_vol_idx=-1, focus_ch_idx=-1):
        self.original_project = project
        self.working_project = self._build_working_copy(project)
        self.ai_config = ai_config

        self._thread = None
        self._cancelled = False
        self._pending_task = None
        self._pending_vol_idx = -1
        self._pending_arc_idx = -1
        self._review_thread = None
        self._pending_review_task = None
        self._pending_revision = None
        self._outline_thread = None
        self._pending_outline_target = None
        self._closing = False

        self._focus_vol_idx = focus_vol_idx
        self._focus_ch_idx = focus_ch_idx

        self.stage_pages = {}
        self._ch_signal_bound = False
        self._current_ch_vol_idx = -1
        self._current_ch_idx = -1
        self._current_vol_idx = -1
        self._current_arc_vol_idx = -1
        self._current_arc_idx = -1

        super().__init__(
            parent,
            title="章节规划",
            subtitle="按「卷 → 弧 → 章」三层拆解，支持批次生成、审核与细纲展开",
            default_size=(1800, 1150),
            min_size=(900, 620),
            show_button_bar=False,
        )

        self._refresh_tree()

        if focus_vol_idx >= 0 and focus_vol_idx < len(self.working_project.volumes):
            self._focus_node(
                ("chapter", focus_vol_idx, focus_ch_idx)
                if focus_ch_idx >= 0 else ("volume", focus_vol_idx)
            )

    @staticmethod
    def _build_working_copy(project):
        wp = StoryProject()
        wp.title = project.title
        wp.settings_book = project.settings_book
        wp.story_background = project.story_background
        wp.premise = project.premise
        wp.power_system = project.power_system
        wp.outline = project.outline
        wp.characters = project.characters
        wp.relations = project.relations
        wp.locations = project.locations
        wp.organizations = project.organizations
        wp.items = project.items
        wp.monsters = getattr(project, "monsters", [])
        wp.volumes = copy.deepcopy(project.volumes)
        return wp

    # ============================================================
    # 内容区
    # ============================================================
    def build_content(self, layout):
        # 顶部工具栏
        top = QHBoxLayout()
        top.setSpacing(SPACING.sm)

        self.extract_btn = QPushButton("从总纲识别分卷")
        self.extract_btn.clicked.connect(self._extract_volumes)
        top.addWidget(self.extract_btn)

        self.arc_btn = QPushButton("拆解本卷为弧")
        self.arc_btn.clicked.connect(self._plan_arcs_for_current_vol)
        self.arc_btn.setEnabled(False)
        top.addWidget(self.arc_btn)

        self.review_arcs_btn = QPushButton("AI 审核本卷弧结构")
        self.review_arcs_btn.clicked.connect(self._review_current_arcs)
        self.review_arcs_btn.setEnabled(False)
        top.addWidget(self.review_arcs_btn)

        self.review_batch_btn = QPushButton("AI 审核本弧已生成章节")
        self.review_batch_btn.clicked.connect(self._review_current_batch)
        self.review_batch_btn.setEnabled(False)
        top.addWidget(self.review_batch_btn)

        self.batch_btn = QPushButton("生成本弧下一批章节")
        self.batch_btn.clicked.connect(self._generate_next_batch)
        self.batch_btn.setEnabled(False)
        top.addWidget(self.batch_btn)

        self.expand_outline_btn = QPushButton("展开本章细纲")
        self.expand_outline_btn.setToolTip(
            "基于章节规划，让 AI 输出细纲与所需实体清单"
        )
        self.expand_outline_btn.clicked.connect(
            self._expand_current_chapter_outline
        )
        self.expand_outline_btn.setEnabled(False)
        top.addWidget(self.expand_outline_btn)

        self.regenerate_arc_btn = QPushButton("重新生成此弧章节")
        self.regenerate_arc_btn.setToolTip(
            "对当前弧的所有章节重新生成；可选择完全重来，"
            "或基于现有内容按指引调整"
        )
        self.regenerate_arc_btn.clicked.connect(
            self._regenerate_current_arc_chapters
        )
        self.regenerate_arc_btn.setEnabled(False)
        top.addWidget(self.regenerate_arc_btn)

        top.addStretch()
        layout.addLayout(top)

        # 主体：左树 + 右编辑区
        splitter = QSplitter(Qt.Horizontal)

        # 左：树
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(SPACING.xs)

        left_layout.addWidget(QLabel("结构树"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemClicked.connect(self._on_tree_item_clicked)
        self.tree.setIndentation(14)
        left_layout.addWidget(self.tree)
        left.setMaximumWidth(380)
        splitter.addWidget(left)

        # 右：页面栈
        self.right_stack = QStackedWidget()
        self._build_empty_page()
        self._build_volume_page()
        self._build_arc_page()
        self._build_chapter_page()
        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        layout.addWidget(splitter, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)

        self.status_label = QLabel("就绪")
        self.status_label.setProperty("role", "hint")
        bar.addWidget(self.status_label)
        bar.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self._on_cancel)
        bar.addWidget(cancel_btn)

        save_btn = QPushButton("保存并返回")
        save_btn.setProperty("role", "primary")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._on_save)
        bar.addWidget(save_btn)

        root_layout.addLayout(bar)

    # ============================================================
    # 右侧页面构建（与旧版逻辑一致，只调整样式相关）
    # ============================================================
    def _build_empty_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addStretch()
        hint = QLabel("请在左侧结构树中选择卷、弧或章节。")
        hint.setAlignment(Qt.AlignCenter)
        hint.setProperty("role", "hint")
        layout.addWidget(hint)
        layout.addStretch()
        self.right_stack.addWidget(page)

    def _build_volume_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(SPACING.sm)

        self.vol_title = QLineEdit()
        form.addRow("卷名:", self.vol_title)

        self.vol_summary = QPlainTextEdit()
        self.vol_summary.setMinimumHeight(120)
        form.addRow("卷摘要:", self.vol_summary)

        form.addRow(HintBox(
            "拆解本卷为弧后，可在左侧展开各弧，逐批生成章节。"
        ))

        self.vol_save_btn = QPushButton("保存卷信息")
        self.vol_save_btn.clicked.connect(self._save_volume_info)
        form.addRow(self.vol_save_btn)

        self.right_stack.addWidget(page)

    def _build_arc_page(self):
        page = QWidget()
        form = QFormLayout(page)
        form.setSpacing(SPACING.sm)

        self.arc_name = QLineEdit()
        form.addRow("弧名:", self.arc_name)

        self.arc_goal = QPlainTextEdit()
        self.arc_goal.setMaximumHeight(130)
        form.addRow("弧目标:", self.arc_goal)

        self.arc_chapters_spin = QSpinBox()
        self.arc_chapters_spin.setRange(3, 30)
        self.arc_chapters_spin.setValue(10)
        form.addRow("预估章数:", self.arc_chapters_spin)

        self.arc_turns = QPlainTextEdit()
        self.arc_turns.setPlaceholderText("每行一个转折点")
        self.arc_turns.setMaximumHeight(150)
        form.addRow("关键转折点:", self.arc_turns)

        self.arc_plant = QPlainTextEdit()
        self.arc_plant.setPlaceholderText("每行一个需埋伏笔")
        self.arc_plant.setMaximumHeight(120)
        form.addRow("需埋伏笔:", self.arc_plant)

        self.arc_payoff = QPlainTextEdit()
        self.arc_payoff.setPlaceholderText("每行一个需回收伏笔")
        self.arc_payoff.setMaximumHeight(120)
        form.addRow("需回收伏笔:", self.arc_payoff)

        self.arc_info = QLabel("")
        self.arc_info.setProperty("role", "hint")
        form.addRow(self.arc_info)

        save_btn = QPushButton("保存弧信息")
        save_btn.clicked.connect(self._save_arc_info)
        form.addRow(save_btn)

        self.right_stack.addWidget(page)

    def _build_chapter_page(self):
        page = QWidget()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        inner = QWidget()
        form = QFormLayout(inner)
        form.setSpacing(SPACING.sm)

        self.ch_title = QLineEdit()
        form.addRow("章节名:", self.ch_title)

        self.ch_goal = QPlainTextEdit()
        self.ch_goal.setMaximumHeight(120)
        form.addRow("本章目标:", self.ch_goal)

        self.ch_characters = QLineEdit()
        self.ch_characters.setPlaceholderText("多个角色用顿号或逗号分隔")
        form.addRow("出场人物:", self.ch_characters)

        self.ch_events = QPlainTextEdit()
        self.ch_events.setPlaceholderText("每行一个关键事件")
        self.ch_events.setMaximumHeight(150)
        form.addRow("关键事件:", self.ch_events)

        self.ch_foreshadow = QPlainTextEdit()
        self.ch_foreshadow.setPlaceholderText("每行一个伏笔")
        self.ch_foreshadow.setMaximumHeight(120)
        form.addRow("伏笔:", self.ch_foreshadow)

        self.ch_hook = QPlainTextEdit()
        self.ch_hook.setMaximumHeight(120)
        form.addRow("结尾钩子:", self.ch_hook)

        self.ch_words = QSpinBox()
        self.ch_words.setRange(500, 20000)
        self.ch_words.setSingleStep(500)
        self.ch_words.setValue(3000)
        form.addRow("预计字数:", self.ch_words)

        # 章节偏好
        pref_row = QHBoxLayout()
        self.ch_preference_combo = QComboBox()
        self.ch_preference_combo.setEditable(True)
        self.ch_preference_combo.setInsertPolicy(QComboBox.NoInsert)
        self.ch_preference_combo.addItem("")
        for p in CHAPTER_PREFERENCES:
            self.ch_preference_combo.addItem(p)
        self.ch_preference_combo.setMinimumWidth(200)
        pref_row.addWidget(self.ch_preference_combo)
        hint = QLabel("（可留空，AI 将自由发挥）")
        hint.setProperty("role", "hint")
        pref_row.addWidget(hint)
        pref_row.addStretch()
        form.addRow("章节偏好:", pref_row)

        # 细纲
        self.ch_outline = QPlainTextEdit()
        self.ch_outline.setPlaceholderText("每行一条场景节拍")
        self.ch_outline.setMinimumHeight(120)
        form.addRow("细纲（每行一条）:", self.ch_outline)

        self.ch_required = QPlainTextEdit()
        self.ch_required.setPlaceholderText(
            "格式示例：\n角色：A、B\n地点：X\n物品：Y\n组织：Z"
        )
        self.ch_required.setMinimumHeight(100)
        form.addRow("所需实体:", self.ch_required)

        self.ch_new_entities = QPlainTextEdit()
        self.ch_new_entities.setPlaceholderText(
            "每行一个，格式：类型｜名称｜描述"
        )
        self.ch_new_entities.setMinimumHeight(90)
        form.addRow("新引入实体（每行一个）:", self.ch_new_entities)

        self.ch_transition = QLineEdit()
        self.ch_transition.setPlaceholderText("一句话说明本章的过渡作用（可选）")
        form.addRow("过渡说明:", self.ch_transition)

        clear_row = QHBoxLayout()
        self.clear_outline_btn = QPushButton("清空细纲")
        self.clear_outline_btn.setProperty("role", "danger")
        self.clear_outline_btn.clicked.connect(self._clear_detailed_outline)
        clear_row.addWidget(self.clear_outline_btn)
        clear_row.addStretch()
        form.addRow("", clear_row)

        self.ch_pos = QLabel("")
        self.ch_pos.setProperty("role", "hint")
        form.addRow(self.ch_pos)

        scroll.setWidget(inner)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)
        self.right_stack.addWidget(page)

    # ============================================================
    # 树
    # ============================================================
    def _refresh_tree(self):
        # 记录刷新前的选中标识（而非 QTreeWidgetItem 对象，对象会被 clear 销毁）
        prev_key = None
        cur = self.tree.currentItem()
        if cur is not None:
            prev_key = cur.data(0, Qt.UserRole)

        self.tree.blockSignals(True)
        self.tree.clear()

        for vi, vol in enumerate(self.working_project.volumes):
            ch_count = len(vol.chapters)
            planned = sum(1 for ch in vol.chapters if ch.plan)
            vol_item = QTreeWidgetItem(self.tree, [
                f"第{vi + 1}卷 {vol.title}  ({planned}/{ch_count})"
            ])
            vol_item.setData(0, Qt.UserRole, ("volume", vi))

            for ai, arc in enumerate(vol.arcs):
                arc_chs = [c for c in vol.chapters if c.arc_idx == ai]
                planned_arc = sum(1 for c in arc_chs if c.plan)
                mark = "◆" if planned_arc >= arc.estimated_chapters else "◇"
                arc_item = QTreeWidgetItem(vol_item, [
                    f"{mark} 弧{ai + 1} {arc.name}  "
                    f"({planned_arc}/{arc.estimated_chapters})"
                ])
                arc_item.setData(0, Qt.UserRole, ("arc", vi, ai))

                for ci, ch in enumerate(vol.chapters):
                    if ch.arc_idx != ai:
                        continue
                    cmark = "◆" if ch.plan else "○"
                    ch_item = QTreeWidgetItem(arc_item, [f"{cmark} {ch.title}"])
                    ch_item.setData(0, Qt.UserRole, ("chapter", vi, ci))

            unassigned = [(i, c) for i, c in enumerate(vol.chapters) if c.arc_idx < 0]
            if unassigned:
                ua_item = QTreeWidgetItem(vol_item, [
                    f"⚠ 未归属章节 ({len(unassigned)})"
                ])
                ua_item.setData(0, Qt.UserRole, ("unassigned", vi))
                for ci, ch in unassigned:
                    cmark = "◆" if ch.plan else "○"
                    ch_item = QTreeWidgetItem(ua_item, [f"{cmark} {ch.title}"])
                    ch_item.setData(0, Qt.UserRole, ("chapter", vi, ci))

            self.tree.expandItem(vol_item)
            for i in range(vol_item.childCount()):
                self.tree.expandItem(vol_item.child(i))

        # 恢复选中（若旧标识仍存在）
        if prev_key is not None:
            restored = self._find_tree_item(prev_key)
            if restored is not None:
                self.tree.setCurrentItem(restored)
                self.tree.scrollToItem(restored)

        self.tree.blockSignals(False)
        self._update_buttons()

    def _find_tree_item(self, key):
        """按 data 元组在树中递归查找节点"""

        def walk(item):
            if item.data(0, Qt.UserRole) == key:
                return item
            for i in range(item.childCount()):
                found = walk(item.child(i))
                if found is not None:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            found = walk(self.tree.topLevelItem(i))
            if found is not None:
                return found
        return None

    def _find_tree_item_by_data(self, target_data):
        """在树中按 data 查找节点"""

        def match(item):
            if item.data(0, Qt.UserRole) == target_data:
                return item
            for i in range(item.childCount()):
                found = match(item.child(i))
                if found:
                    return found
            return None

        for i in range(self.tree.topLevelItemCount()):
            root = self.tree.topLevelItem(i)
            found = match(root)
            if found:
                return found
        return None

    def _focus_node(self, key):
        """展开并选中节点"""
        for i in range(self.tree.topLevelItemCount()):
            vi_item = self.tree.topLevelItem(i)
            data = vi_item.data(0, Qt.UserRole)
            if key[0] == "volume" and data == ("volume", key[1]):
                self.tree.setCurrentItem(vi_item)
                self._on_tree_item_clicked(vi_item, 0)
                return
            for j in range(vi_item.childCount()):
                child = vi_item.child(j)
                cdata = child.data(0, Qt.UserRole)
                if key[0] == "arc" and cdata == ("arc", key[1], key[2]):
                    self.tree.setCurrentItem(child)
                    self._on_tree_item_clicked(child, 0)
                    return
                for k in range(child.childCount()):
                    gchild = child.child(k)
                    gdata = gchild.data(0, Qt.UserRole)
                    if (key[0] == "chapter" and gdata
                            and gdata[0] == "chapter"
                            and gdata[1] == key[1] and gdata[2] == key[2]):
                        self.tree.setCurrentItem(gchild)
                        self._on_tree_item_clicked(gchild, 0)
                        return

    def _on_tree_item_clicked(self, item, col):
        data = item.data(0, Qt.UserRole)
        if not data:
            self.right_stack.setCurrentIndex(0)
            self._update_buttons()
            return

        if data[0] == "volume":
            self._show_volume_page(data[1])
        elif data[0] == "arc":
            self._show_arc_page(data[1], data[2])
        elif data[0] == "chapter":
            self._show_chapter_page(data[1], data[2])
        elif data[0] == "unassigned":
            self.right_stack.setCurrentIndex(0)
        self._update_buttons()

    def _update_buttons(self):
        item = self.tree.currentItem()
        data = item.data(0, Qt.UserRole) if item else None
        volumes = self.working_project.volumes

        # ---- 卷按钮 ----
        if data and data[0] == "volume" and 0 <= data[1] < len(volumes):
            self.arc_btn.setVisible(True)
            self.arc_btn.setEnabled(True)
            self.arc_btn.setText("拆解本卷为弧")
            vol = volumes[data[1]]
            self.review_arcs_btn.setVisible(len(vol.arcs) > 0)
            self.review_arcs_btn.setEnabled(len(vol.arcs) > 0)
            self.review_batch_btn.setEnabled(False)
            self.review_batch_btn.setVisible(False)
        else:
            self.arc_btn.setVisible(False)
            self.arc_btn.setEnabled(False)
            self.review_arcs_btn.setVisible(False)
            self.review_arcs_btn.setEnabled(False)

        # ---- 弧按钮 ----
        if data and data[0] == "arc" and 0 <= data[1] < len(volumes):
            vi, ai = data[1], data[2]
            vol = volumes[vi]
            self.batch_btn.setVisible(True)
            self.review_batch_btn.setVisible(True)
            if 0 <= ai < len(vol.arcs):
                arc = vol.arcs[ai]
                done = len([c for c in vol.chapters if c.arc_idx == ai])
                self.regenerate_arc_btn.setVisible(done > 0)
                self.regenerate_arc_btn.setEnabled(done > 0)
                if done < arc.estimated_chapters:
                    self.batch_btn.setEnabled(True)
                    remain = arc.estimated_chapters - done
                    batch = min(BATCH_SIZE, remain)
                    self.batch_btn.setText(f"生成本弧下一批章节 ({batch}章)")
                else:
                    self.batch_btn.setVisible(False)
                    self.batch_btn.setEnabled(False)
                    self.batch_btn.setText("本弧已完成")
                self.review_batch_btn.setEnabled(done > 0)
            else:
                # 弧被删除/重建导致索引失效
                self.batch_btn.setVisible(False)
                self.batch_btn.setEnabled(False)
                self.batch_btn.setText("生成本弧下一批章节")
                self.review_batch_btn.setEnabled(False)
                self.regenerate_arc_btn.setEnabled(False)
        else:
            self.batch_btn.setVisible(False)
            self.batch_btn.setEnabled(False)
            self.regenerate_arc_btn.setVisible(False)
            self.regenerate_arc_btn.setEnabled(False)
            self.batch_btn.setText("生成本弧下一批章节")
            if not (data and data[0] == "volume"):
                self.review_batch_btn.setEnabled(False)

        # ---- 细纲按钮 ----
        outline_enabled = False
        self.expand_outline_btn.setVisible(False)
        if data and data[0] == "chapter" and 0 <= data[1] < len(volumes):
            vi, ci = data[1], data[2]
            vol = volumes[vi]
            self.expand_outline_btn.setVisible(True)
            if 0 <= ci < len(vol.chapters):
                outline_enabled = vol.chapters[ci].plan is not None
        elif self._current_ch_vol_idx >= 0 and self._current_ch_idx >= 0:
            vi, ci = self._current_ch_vol_idx, self._current_ch_idx
            if 0 <= vi < len(volumes):
                vol = volumes[vi]
                if 0 <= ci < len(vol.chapters):
                    outline_enabled = vol.chapters[ci].plan is not None
        self.expand_outline_btn.setEnabled(outline_enabled)

        # 审核流程进行中，禁用相关按钮
        review_in_progress = (
                self._pending_review_task is not None
                or (self._review_thread and self._review_thread.isRunning())
        )
        if review_in_progress:
            self.review_arcs_btn.setEnabled(False)
            self.review_batch_btn.setEnabled(False)
            self.regenerate_arc_btn.setEnabled(False)

    def _reset_top_buttons(self):
        self._pending_review_task = None
        self.extract_btn.setEnabled(True)
        self.extract_btn.setText("从总纲识别分卷")
        self.arc_btn.setText("拆解本卷为弧")
        self.batch_btn.setText("生成本弧下一批章节")
        if hasattr(self, "review_batch_btn"):
            self.review_batch_btn.setText("AI 审核本弧已生成章节")
        self._update_buttons()

    # ============================================================
    # 页面显示
    # ============================================================
    def _show_volume_page(self, vi):
        vol = self.working_project.volumes[vi]
        self._current_vol_idx = vi
        self.vol_title.setText(vol.title)
        self.vol_summary.setPlainText(vol.summary)
        self.right_stack.setCurrentIndex(1)

    def _show_arc_page(self, vi, ai):
        vol = self.working_project.volumes[vi]
        if ai >= len(vol.arcs):
            return
        arc = vol.arcs[ai]
        self._current_arc_vol_idx = vi
        self._current_arc_idx = ai

        self.arc_name.setText(arc.name)
        self.arc_goal.setPlainText(arc.goal)
        self.arc_chapters_spin.setValue(arc.estimated_chapters)
        self.arc_turns.setPlainText("\n".join(arc.key_turning_points))
        self.arc_plant.setPlainText("\n".join(arc.foreshadowing_to_plant))
        self.arc_payoff.setPlainText("\n".join(arc.foreshadowing_to_payoff))

        done = len([c for c in vol.chapters if c.arc_idx == ai])
        self.arc_info.setText(
            f"进度：{done}/{arc.estimated_chapters} 章已规划"
        )
        self.right_stack.setCurrentIndex(2)

    def _show_chapter_page(self, vi, ci, skip_save=False):
        """
        加载章节编辑页。
        skip_save=True：跳过"保存上一个页面"逻辑，用于 AI 结果写入后刷新，
        避免用旧 UI 覆盖刚写入的 chapter.plan。
        """
        # 切换前先保存上一个页面的编辑（跳过时不做）
        if self._ch_signal_bound and not skip_save:
            try:
                self._save_chapter_form()
            except Exception:
                pass

        # 无论哪种情况，先断开信号，避免 setText 触发保存
        self._bind_chapter_signals(False)

        vol = self.working_project.volumes[vi]
        if ci >= len(vol.chapters):
            return
        ch = vol.chapters[ci]
        self._current_ch_vol_idx = vi
        self._current_ch_idx = ci

        plan = ch.plan or ChapterPlan()
        self.ch_title.setText(plan.title or ch.title)
        self.ch_goal.setPlainText(plan.goal)
        self.ch_characters.setText("、".join(plan.characters))
        self.ch_events.setPlainText("\n".join(plan.key_events))
        self.ch_foreshadow.setPlainText("\n".join(plan.foreshadowing))
        self.ch_hook.setPlainText(plan.ending_hook)
        self.ch_words.setValue(plan.estimated_words or 3000)
        # 章节偏好
        self.ch_preference_combo.blockSignals(True)
        self.ch_preference_combo.setCurrentText(
            plan.chapter_preference or ""
        )
        self.ch_preference_combo.blockSignals(False)

        # 细纲相关
        self.ch_outline.setPlainText("\n".join(plan.detailed_outline or []))
        self.ch_required.setPlainText(
            self._format_required_entities(plan.required_entities)
        )
        self.ch_new_entities.setPlainText(
            self._format_new_entities(
                plan.required_entities.get("new_entities") or []
            )
        )
        self.ch_transition.setText(plan.transition_notes or "")
        self.clear_outline_btn.setEnabled(bool(plan.detailed_outline))

        arc_note = ""
        if ch.arc_idx >= 0 and ch.arc_idx < len(vol.arcs):
            arc_note = f" · 属于：弧{ch.arc_idx + 1} {vol.arcs[ch.arc_idx].name}"
        self.ch_pos.setText(
            f"第{vi + 1}卷 · 第{ci + 1}章{arc_note}"
        )

        # 重新绑定信号
        self._bind_chapter_signals(True)
        self.right_stack.setCurrentIndex(3)

    def _bind_chapter_signals(self, on):
        if on and not self._ch_signal_bound:
            self.ch_title.textChanged.connect(self._save_chapter_form)
            self.ch_goal.textChanged.connect(self._save_chapter_form)
            self.ch_characters.textChanged.connect(self._save_chapter_form)
            self.ch_events.textChanged.connect(self._save_chapter_form)
            self.ch_foreshadow.textChanged.connect(self._save_chapter_form)
            self.ch_hook.textChanged.connect(self._save_chapter_form)
            self.ch_words.valueChanged.connect(self._save_chapter_form)
            self.ch_preference_combo.currentTextChanged.connect(
                self._save_chapter_form
            )
            # 细纲相关
            self.ch_outline.textChanged.connect(self._save_chapter_form)
            self.ch_required.textChanged.connect(self._save_chapter_form)
            self.ch_transition.textChanged.connect(self._save_chapter_form)
            self.ch_new_entities.textChanged.connect(self._save_chapter_form)
            self._ch_signal_bound = True
        elif not on and self._ch_signal_bound:
            try:
                self.ch_title.textChanged.disconnect()
                self.ch_goal.textChanged.disconnect()
                self.ch_characters.textChanged.disconnect()
                self.ch_events.textChanged.disconnect()
                self.ch_foreshadow.textChanged.disconnect()
                self.ch_hook.textChanged.disconnect()
                self.ch_words.valueChanged.disconnect()
                self.ch_preference_combo.currentTextChanged.disconnect()
                self.ch_outline.textChanged.disconnect()
                self.ch_required.textChanged.disconnect()
                self.ch_transition.textChanged.disconnect()
                self.ch_new_entities.textChanged.disconnect()
            except Exception:
                pass
            self._ch_signal_bound = False

    # ============================================================
    # 表单保存
    # ============================================================
    def _save_volume_info(self):
        vi = self._current_vol_idx
        if vi < 0:
            return
        vol = self.working_project.volumes[vi]
        vol.title = self.vol_title.text().strip() or vol.title
        vol.summary = self.vol_summary.toPlainText()
        self._refresh_tree()

    def _save_arc_info(self):
        vi = self._current_arc_vol_idx
        ai = self._current_arc_idx
        if vi < 0 or ai < 0:
            return
        vol = self.working_project.volumes[vi]
        if ai >= len(vol.arcs):
            return
        arc = vol.arcs[ai]
        arc.name = self.arc_name.text().strip() or arc.name
        arc.goal = self.arc_goal.toPlainText()
        arc.estimated_chapters = self.arc_chapters_spin.value()
        arc.key_turning_points = [
            x.strip() for x in self.arc_turns.toPlainText().splitlines() if x.strip()
        ]
        arc.foreshadowing_to_plant = [
            x.strip() for x in self.arc_plant.toPlainText().splitlines() if x.strip()
        ]
        arc.foreshadowing_to_payoff = [
            x.strip() for x in self.arc_payoff.toPlainText().splitlines() if x.strip()
        ]
        self._refresh_tree()

    def _save_chapter_form(self):
        vi = self._current_ch_vol_idx
        ci = self._current_ch_idx
        if vi < 0 or ci < 0:
            return
        vol = self.working_project.volumes[vi]
        if ci >= len(vol.chapters):
            return
        ch = vol.chapters[ci]

        def split_lines(text):
            return [x.strip() for x in text.splitlines() if x.strip()]

        def split_chars(text):
            for sep in ("、", ",", "，", ";", "；"):
                if sep in text:
                    return [x.strip() for x in text.split(sep) if x.strip()]
            return [text.strip()] if text.strip() else []

        # 保留旧 plan 中通过 UI 编辑的字段（new_entities / outline_thought）
        old_plan = ch.plan
        old_thought = ""
        if old_plan:
            old_thought = old_plan.outline_thought or ""

        # 从 UI 读取细纲相关字段
        detailed_outline = split_lines(self.ch_outline.toPlainText())
        required_entities = self._parse_required_entities(
            self.ch_required.toPlainText()
        )
        # 从 UI 解析 new_entities（若用户清空则为空）
        required_entities["new_entities"] = self._parse_new_entities(
            self.ch_new_entities.toPlainText()
        )
        transition_notes = self.ch_transition.text().strip()

        chapter_preference = self.ch_preference_combo.currentText().strip()

        title = self.ch_title.text().strip()
        plan = ChapterPlan(
            title=title,
            goal=self.ch_goal.toPlainText().strip(),
            characters=split_chars(self.ch_characters.text()),
            key_events=split_lines(self.ch_events.toPlainText()),
            foreshadowing=split_lines(self.ch_foreshadow.toPlainText()),
            ending_hook=self.ch_hook.toPlainText().strip(),
            estimated_words=self.ch_words.value(),
            detailed_outline=detailed_outline,
            required_entities=required_entities,
            transition_notes=transition_notes,
            chapter_preference=chapter_preference,
            outline_thought=old_thought,
        )
        ch.plan = plan
        if title:
            ch.title = title

        # 更新清空按钮状态
        self.clear_outline_btn.setEnabled(bool(detailed_outline))

        self._refresh_tree()

    # ============================================================
    # 从总纲识别分卷
    # ============================================================
    def _extract_volumes(self):
        if not (self.working_project.outline or self.working_project.story_background):
            QMessageBox.information(
                self, "提示",
                "尚无故事总纲或故事背景，无法识别分卷。\n"
                "请先通过「AI 策划」生成设定。"
            )
            return
        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return
        reply = QMessageBox.question(
            self, "确认",
            "将从故事总纲识别分卷。\n"
            "若已有分卷，识别结果会覆盖卷名与卷摘要，但不会删除已有章节。\n"
            "是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self.extract_btn.setEnabled(False)
        self.extract_btn.setText("识别中...")

        prompt = build_volume_extraction_prompt(self.working_project)
        self._start_async("volumes", None, prompt, max_tokens=8192*2)

    # ============================================================
    # 拆解卷为弧
    # ============================================================
    def _plan_arcs_for_current_vol(self):
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "volume":
            return
        vi = data[1]
        vol = self.working_project.volumes[vi]

        if vol.arcs:
            reply = QMessageBox.question(
                self, "确认",
                f"《{vol.title}》已有 {len(vol.arcs)} 个弧。\n"
                "重新拆解会覆盖弧信息，已有章节的弧归属会重置。\n"
                "是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        self.arc_btn.setEnabled(False)
        self.arc_btn.setText("拆解中...")
        self._pending_vol_idx = vi

        prompt = build_arc_planning_prompt(
            self.working_project, vi,
            enable_golden_three=getattr(
                self.ai_config, "enable_golden_three_chapters", False
            ),
        )
        self._start_async("arcs", vi, prompt, max_tokens=8192*8)

    # ============================================================
    # 生成下一批章节
    # ============================================================
    def _generate_next_batch(self):
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "arc":
            return
        vi, ai = data[1], data[2]
        vol = self.working_project.volumes[vi]
        if ai >= len(vol.arcs):
            return
        arc = vol.arcs[ai]

        done = len([c for c in vol.chapters if c.arc_idx == ai])
        if done >= arc.estimated_chapters:
            QMessageBox.information(self, "提示", "本弧已完成。")
            return

        remain = arc.estimated_chapters - done
        batch = min(BATCH_SIZE, remain)

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        self.batch_btn.setEnabled(False)
        self.batch_btn.setText("生成中...")
        self._pending_vol_idx = vi
        self._pending_arc_idx = ai

        try:
            prompt = build_arc_chapters_prompt(
                self.working_project, vi, ai,
                batch_start=done, batch_size=batch,
                enable_golden_three=getattr(
                    self.ai_config, "enable_golden_three_chapters", False
                ),
            )
        except Exception as e:
            QMessageBox.warning(self, "提示", f"构建 prompt 失败：{e}")
            self._update_buttons()
            return

        self._start_async("chapters", (vi, ai, done), prompt, max_tokens=8192*10)

    def _regenerate_current_arc_chapters(self):
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "arc":
            return
        vi, ai = data[1], data[2]
        vol = self.working_project.volumes[vi]
        if not (0 <= ai < len(vol.arcs)):
            return
        arc = vol.arcs[ai]

        existing = [c for c in vol.chapters if c.arc_idx == ai]
        if not existing:
            QMessageBox.information(
                self, "提示",
                "该弧还没有章节，请使用「生成本弧下一批章节」。"
            )
            return

        if self._thread and self._thread.isRunning():
            QMessageBox.information(
                self, "提示", "请等待当前任务完成。"
            )
            return

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        # 下游弧提示（不改动下游，仅作信息展示）
        downstream = []
        for j in range(ai + 1, len(vol.arcs)):
            next_arc = vol.arcs[j]
            next_done = sum(1 for c in vol.chapters if c.arc_idx == j)
            if next_done > 0:
                downstream.append(
                    f"弧{j + 1} {next_arc.name}（{next_done} 章，不受影响）"
                )

        extra_hint = (
            f"清空该弧下 {len(existing)} 章规划后，从头生成整弧章节。\n"
            "已写章节的正文内容会按标题匹配保留；标题变化的章节正文会丢失。"
        )

        dlg = RegenerateStageDialog(
            stage_label=f"弧{ai + 1} {arc.name}",
            has_content=True,
            downstream_stages=downstream,
            parent=self,
            extra_fresh_hint=extra_hint,
        )
        if dlg.exec_() != QDialog.Accepted:
            return

        mode, guidance = dlg.get_result()
        self._start_arc_regenerate(vi, ai, mode, guidance, existing)

    def _start_arc_regenerate(self, vi, ai, mode, guidance, existing):
        """
        启动整弧重新生成。
        - fresh：不传参考章节，清空后重建
        - optimize：传参考章节 + 指引
        生成成功后才替换章节；失败时现有章节不受影响。
        """
        vol = self.working_project.volumes[vi]
        arc = vol.arcs[ai]

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        self.batch_btn.setEnabled(False)
        self.regenerate_arc_btn.setEnabled(False)
        self.batch_btn.setText("生成中...")
        self.status_label.setText(
            f"AI 正在{'重新生成' if mode == 'fresh' else '按指引调整'}"
            f"《{arc.name}》的整弧章节..."
        )

        try:
            prompt = build_arc_chapters_prompt(
                self.working_project, vi, ai,
                batch_start=0,
                batch_size=arc.estimated_chapters,
                enable_golden_three=getattr(
                    self.ai_config, "enable_golden_three_chapters", False
                ),
                existing_chapters=existing if mode == "optimize" else None,
                user_guidance=guidance if mode == "optimize" else "",
            )
        except Exception as e:
            QMessageBox.warning(self, "提示", f"构建 prompt 失败：{e}")
            self._update_buttons()
            self.status_label.setText("就绪")
            return

        self._pending_task = ("regenerate_chapters", (vi, ai, mode))

        self._thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192 * 10, json_mode=True, timeout=600,
        )
        self._thread.finished.connect(self._on_async_finished)
        self._thread.error.connect(self._on_async_error)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    # ============================================================
    # 异步任务
    # ============================================================
    def _start_async(self, task_type, payload, prompt, max_tokens=8192*4):
        if self._thread and self._thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前任务完成。")
            return

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            self._update_buttons()
            return

        self._pending_task = (task_type, payload)
        self.status_label.setText("AI 处理中...")

        self._thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=max_tokens, json_mode=True, timeout=240,
        )
        self._thread.finished.connect(self._on_async_finished)
        self._thread.error.connect(self._on_async_error)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _on_async_finished(self, text):
        self._thread = None
        if self._closing:
            return
        task = self._pending_task
        self._pending_task = None
        if not task:
            return
        task_type, payload = task

        try:
            if task_type == "volumes":
                self._handle_volumes_result(text)
            elif task_type == "arcs":
                self._handle_arcs_result(payload, text)
            elif task_type == "chapters":
                self._handle_chapters_result(payload, text)
            elif task_type == "regenerate_chapters":
                self._handle_arc_regenerate_result(payload, text)
        except Exception as e:
            QMessageBox.warning(self, "处理失败", str(e))
        finally:
            self._refresh_tree()  # 先清空 currentItem，避免访问失效索引
            self._reset_top_buttons()  # 再重置按钮（此时 currentItem 已为 None）
            self.status_label.setText("就绪")

    def _on_async_error(self, err):
        self._thread = None
        if self._closing:
            return
        task = self._pending_task
        self._pending_task = None
        self._reset_top_buttons()
        self.status_label.setText(f"失败：{err}")

        is_regenerate = task and task[0] == "regenerate_chapters"

        if "被截断" in err or "max_tokens" in err:
            if is_regenerate:
                QMessageBox.warning(
                    self, "输出截断",
                    "整弧重新生成的输出被截断。\n\n"
                    "建议：\n"
                    "① 减少该弧的预估章数（在弧信息中调整）\n"
                    "② 改用「生成本弧下一批章节」分批生成\n"
                    "③ 缩短每章规划的内容（目标、关键事件尽量简洁）"
                )
            else:
                QMessageBox.warning(
                    self, "输出截断",
                    "AI 输出被截断。\n"
                    "建议减少本批章节数或缩短每章规划内容后重试。"
                )
        else:
            QMessageBox.warning(self, "AI 错误", err)

    def _reset_top_buttons(self):
        self.extract_btn.setEnabled(True)
        self.extract_btn.setText("从总纲识别分卷")
        self.arc_btn.setText("拆解本卷为弧")
        self.batch_btn.setText("生成本弧下一批章节")
        self._update_buttons()

    # ============================================================
    # 结果处理
    # ============================================================
    def _handle_volumes_result(self, text):
        volumes = parse_volume_response(text)
        if not volumes:
            QMessageBox.information(self, "提示", "未识别到分卷。")
            return

        existing = {v.title: v for v in self.working_project.volumes}
        new_vols = []
        for v in volumes:
            old = existing.get(v["title"])
            if old:
                old.summary = v["summary"] or old.summary
                new_vols.append(old)
            else:
                new_vols.append(Volume(title=v["title"], summary=v["summary"]))
        self.working_project.volumes = new_vols
        QMessageBox.information(
            self, "完成",
            f"已识别 {len(volumes)} 个分卷。\n"
            "请在左侧选择分卷，点击「拆解本卷为弧」。"
        )

    def _handle_arcs_result(self, vol_idx, text):
        arcs = parse_arc_response(text)
        if not arcs:
            QMessageBox.information(self, "提示", "未识别到故事弧。")
            return

        vol = self.working_project.volumes[vol_idx]
        vol.arcs = [StoryArc(
            name=a["name"],
            goal=a["goal"],
            estimated_chapters=a["estimated_chapters"],
            key_turning_points=a["key_turning_points"],
            foreshadowing_to_plant=a["foreshadowing_to_plant"],
            foreshadowing_to_payoff=a["foreshadowing_to_payoff"],
        ) for a in arcs]

        # 已有章节的弧归属重置
        for ch in vol.chapters:
            ch.arc_idx = -1

        QMessageBox.information(
            self, "完成",
            f"《{vol.title}》已拆解为 {len(arcs)} 个弧。\n"
            "请在左侧选择弧，逐批生成章节规划。"
        )

        # 新增：主动清空选中，避免残留旧数据
        self.tree.blockSignals(True)
        self.tree.clearSelection()
        self.tree.setCurrentItem(None)
        self.tree.blockSignals(False)

    def _handle_chapters_result(self, payload, text):
        vol_idx, arc_idx, batch_start = payload
        plans = parse_chapter_plan_response(text)
        if not plans:
            QMessageBox.information(self, "提示", "未生成任何章节。")
            return

        vol = self.working_project.volumes[vol_idx]
        arc = vol.arcs[arc_idx]

        # 保留已有正文（按标题匹配）
        existing_content = {ch.title: ch.content for ch in vol.chapters}

        added = 0
        for p in plans:
            ch = Chapter(
                title=p["title"],
                content=existing_content.get(p["title"], ""),
                summary="",
                arc_idx=arc_idx,
            )
            ch.plan = ChapterPlan(
                title=p["title"],
                goal=p["goal"],
                characters=p["characters"],
                key_events=p["key_events"],
                foreshadowing=p["foreshadowing"],
                ending_hook=p["ending_hook"],
                estimated_words=p["estimated_words"],
            )
            vol.chapters.append(ch)
            added += 1

        done = len([c for c in vol.chapters if c.arc_idx == arc_idx])
        remain = arc.estimated_chapters - done

        msg = (
            f"弧《{arc.name}》新增 {added} 章规划。\n"
            f"进度：{done}/{arc.estimated_chapters}"
        )
        if remain > 0:
            msg += f"\n还剩 {remain} 章，可继续点击「生成本弧下一批章节」。"
        QMessageBox.information(self, "完成", msg)

    def _handle_arc_regenerate_result(self, payload, text):
        vol_idx, arc_idx, mode = payload
        plans = parse_chapter_plan_response(text)
        if not plans:
            QMessageBox.information(self, "提示", "未生成任何章节。")
            return

        vol = self.working_project.volumes[vol_idx]
        arc = vol.arcs[arc_idx]

        # 收集现有正文（按标题匹配保留）
        existing_content = {}
        for ch in vol.chapters:
            if ch.arc_idx == arc_idx and (ch.content or "").strip():
                existing_content[ch.title] = ch.content

        # 清空该弧下所有章节
        vol.chapters = [c for c in vol.chapters if c.arc_idx != arc_idx]

        # 写入新章节
        added = 0
        for p in plans:
            ch = Chapter(
                title=p["title"],
                content=existing_content.get(p["title"], ""),
                summary="",
                arc_idx=arc_idx,
            )
            ch.plan = ChapterPlan(
                title=p["title"],
                goal=p["goal"],
                characters=p["characters"],
                key_events=p["key_events"],
                foreshadowing=p["foreshadowing"],
                ending_hook=p["ending_hook"],
                estimated_words=p["estimated_words"],
            )
            vol.chapters.append(ch)
            added += 1

        done = len([c for c in vol.chapters if c.arc_idx == arc_idx])

        action = "重新生成" if mode == "fresh" else "按指引调整"
        msg = (
            f"弧《{arc.name}》已{action} {added} 章规划。\n"
            f"进度：{done}/{arc.estimated_chapters}"
        )
        if existing_content:
            kept = sum(1 for p in plans if p["title"] in existing_content)
            lost = len(existing_content) - kept
            if kept:
                msg += f"\n已保留 {kept} 章原有正文（按标题匹配）"
            if lost > 0:
                msg += f"\n注意：{lost} 章原有正文因标题变化已丢失"

        QMessageBox.information(self, "完成", msg)

    # ============================================================
    # 展开细纲
    # ============================================================
    def _expand_current_chapter_outline(self):
        """为当前选中的章节展开细纲"""
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "chapter":
            return
        vi, ci = data[1], data[2]
        vol = self.working_project.volumes[vi]
        if ci >= len(vol.chapters):
            return
        ch = vol.chapters[ci]

        if not ch.plan:
            QMessageBox.information(self, "提示", "本章尚无规划，请先生成规划。")
            return

        if ch.plan.has_detailed_outline():
            reply = QMessageBox.question(
                self, "确认",
                "本章已有细纲，重新展开会覆盖现有细纲。\n是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "策划 Agent 未配置 API Key。")
            return

        from .detailed_outliner import build_detailed_outline_prompt
        prompt = build_detailed_outline_prompt(
            self.working_project, vi, ci,
            enable_golden_three=getattr(
                self.ai_config, "enable_golden_three_chapters", False
            ),
        )
        if not prompt:
            QMessageBox.information(self, "提示", "无法构建细纲 prompt。")
            return

        self._pending_outline_target = (vi, ci)
        self.expand_outline_btn.setEnabled(False)
        self.expand_outline_btn.setText("展开中...")
        self.status_label.setText(
            f"正在为第{vi + 1}卷 第{ci + 1}章 展开细纲..."
        )

        self._outline_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*6, json_mode=True, timeout=180,
        )
        self._outline_thread.finished.connect(self._on_outline_finished)
        self._outline_thread.error.connect(self._on_outline_error)
        self._outline_thread.finished.connect(self._outline_thread.deleteLater)
        self._outline_thread.start()

    def _on_outline_finished(self, text):
        self._outline_thread = None
        if self._closing:
            return
        target = self._pending_outline_target
        self._pending_outline_target = None
        self.expand_outline_btn.setText("展开本章细纲")
        self._update_buttons()
        self.status_label.setText("就绪")

        if not target:
            return
        vi, ci = target

        from .detailed_outliner import (
            parse_detailed_outline_response,
            apply_detailed_outline,
        )
        try:
            result = parse_detailed_outline_response(text)
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"细纲解析失败：{e}")
            return

        # 写入 working_project 的 chapter.plan
        apply_detailed_outline(self.working_project, vi, ci, result)

        # 刷新树（不影响 plan 数据）
        self._refresh_tree()

        # 关键：skip_save=True，避免用旧 UI 覆盖刚写入的细纲
        self._show_chapter_page(vi, ci, skip_save=True)

        n_chars = len(result["required_entities"].get("characters", []))
        n_monsters = len(result["required_entities"].get("monsters", []))
        n_locs = len(result["required_entities"].get("locations", []))
        n_items = len(result["required_entities"].get("items", []))
        n_orgs = len(result["required_entities"].get("organizations", []))
        n_new = len(result["required_entities"].get("new_entities", []))
        QMessageBox.information(
            self, "完成",
            f"细纲已生成：{len(result['detailed_outline'])} 个场景节拍\n"
            f"所需实体：角色 {n_chars}/ 怪物 {n_monsters} / 地点 {n_locs} / "
            f"物品 {n_items} / 组织 {n_orgs}"
            + (f" / 新引入 {n_new}" if n_new else "")
        )

    def _on_outline_error(self, err):
        self._outline_thread = None
        if self._closing:
            return
        self._pending_outline_target = None
        self.expand_outline_btn.setText("展开本章细纲")
        self._update_buttons()
        self.status_label.setText("就绪")
        QMessageBox.warning(self, "AI 错误", f"展开细纲失败：{err}")

    # ============================================================
    # 细纲辅助
    # ============================================================
    def _format_required_entities(self, required: dict) -> str:
        """把 required_entities 中的五类名单转为可编辑文本（不含 new_entities）"""
        if not required:
            return ""
        lines = []
        for key, label in [
            ("characters", "角色"),
            ("locations", "地点"),
            ("monsters", "怪物"),
            ("items", "物品"),
            ("organizations", "组织"),
        ]:
            names = required.get(key) or []
            if names:
                lines.append(f"{label}：{'、'.join(names)}")
        return "\n".join(lines)

    def _parse_required_entities(self, text: str) -> dict:
        """把编辑文本解析回 required_entities dict（不含 new_entities）"""
        required = {
            "characters": [],
            "monsters": [],
            "locations": [],
            "items": [],
            "organizations": [],
            "new_entities": [],
        }
        label_map = {
            "角色": "characters",
            "怪物": "monsters",
            "地点": "locations",
            "物品": "items",
            "组织": "organizations",
        }
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            # 支持中英文冒号
            sep = "：" if "：" in line else (":" if ":" in line else None)
            if not sep:
                continue
            label, _, content = line.partition(sep)
            label = label.strip()
            if label not in label_map:
                continue
            names = [
                x.strip() for x in content.replace(",", "、").split("、")
                if x.strip()
            ]
            required[label_map[label]] = names
        return required

    def _format_new_entities(self, new_entities) -> str:
        """把 new_entities 列表转为可编辑文本（类型｜名称｜描述）"""
        if not new_entities:
            return ""
        type_map = {
            "character": "角色",
            "monsters": "怪物",
            "location": "地点",
            "item": "物品",
            "organization": "组织",
        }
        lines = []
        for e in new_entities:
            if not isinstance(e, dict):
                continue
            typ = type_map.get(e.get("type", ""), e.get("type", ""))
            name = (e.get("name") or "").strip()
            desc = (e.get("description") or "").strip()
            if not name:
                continue
            line = f"{typ}｜{name}"
            if desc:
                line += f"｜{desc}"
            lines.append(line)
        return "\n".join(lines)

    def _parse_new_entities(self, text: str) -> list:
        """把编辑文本解析回 new_entities 列表"""
        type_map_rev = {
            "角色": "character",
            "character": "character",
            "怪物": "monsters",
            "monsters": "monsters",
            "地点": "location",
            "location": "location",
            "物品": "item",
            "item": "item",
            "组织": "organization",
            "organization": "organization",
        }
        result = []
        for line in (text or "").splitlines():
            line = line.strip()
            if not line:
                continue
            # 支持全角/半角竖线作为分隔
            sep = None
            for s in ("｜", "|"):
                if s in line:
                    sep = s
                    break
            if sep is None:
                continue
            parts = [x.strip() for x in line.split(sep)]
            if len(parts) < 2:
                continue
            typ_raw = parts[0]
            typ = type_map_rev.get(typ_raw) or type_map_rev.get(typ_raw.lower())
            if not typ:
                continue
            name = parts[1]
            if not name:
                continue
            desc = parts[2] if len(parts) > 2 else ""
            result.append({
                "type": typ,
                "name": name,
                "description": desc,
            })
        return result

    def _clear_detailed_outline(self):
        """清空当前章节的细纲相关字段"""
        vi = self._current_ch_vol_idx
        ci = self._current_ch_idx
        if vi < 0 or ci < 0:
            return
        vol = self.working_project.volumes[vi]
        if ci >= len(vol.chapters):
            return
        ch = vol.chapters[ci]
        if not ch.plan:
            return
        if not (ch.plan.detailed_outline or ch.plan.required_entities
                or ch.plan.transition_notes):
            QMessageBox.information(self, "提示", "本章尚未展开细纲。")
            return

        reply = QMessageBox.question(
            self, "确认清空",
            "确定要清空本章的细纲、实体清单与过渡说明吗？\n"
            "此操作不可撤销，如需恢复需重新展开。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        ch.plan.detailed_outline = []
        ch.plan.required_entities = {}
        ch.plan.transition_notes = ""
        ch.plan.outline_thought = ""

        # 关键：skip_save=True，避免清空前的 UI 又被保存回来
        self._show_chapter_page(vi, ci, skip_save=True)
        QMessageBox.information(self, "已清空", "本章细纲已清空。")

    # ============================================================
    # 底部按钮
    # ============================================================
    def _on_save(self):
        # 校验弧归属
        warnings = []
        for vi, vol in enumerate(self.working_project.volumes):
            valid = set(range(len(vol.arcs)))
            unassigned = []
            for ci, ch in enumerate(vol.chapters):
                if ch.arc_idx < 0:
                    unassigned.append(ch.title)
                elif ch.arc_idx not in valid:
                    warnings.append(
                        f"第{vi + 1}卷《{vol.title}》第{ci + 1}章 {ch.title}："
                        f"弧索引 {ch.arc_idx} 越界，将被重置为未分类"
                    )
                    ch.arc_idx = -1
            if unassigned:
                warnings.append(
                    f"第{vi + 1}卷《{vol.title}》有 {len(unassigned)} 章未归属到任何弧，"
                    "将显示在「未归属章节」分组"
                )

        total = 0
        planned = 0
        for vol in self.working_project.volumes:
            for ch in vol.chapters:
                total += 1
                if ch.plan:
                    planned += 1

        msg = (
            f"即将把章节规划写回项目：\n"
            f"- 共 {len(self.working_project.volumes)} 卷，{total} 章\n"
            f"- 已完成规划：{planned} 章\n"
        )
        if warnings:
            msg += "\n【提醒】\n" + "\n".join(warnings) + "\n"
        msg += "\n是否确认保存？"

        reply = QMessageBox.question(
            self, "确认保存", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self.original_project.volumes = self.working_project.volumes
        self.accept()

    def _on_cancel(self):
        self.reject()

    def reject(self):
        self._closing = True
        self._cancelled = True
        self._pending_task = None
        self._pending_review_task = None
        self._pending_revision = None
        self._pending_outline_target = None

        for attr in ("_review_thread", "_thread", "_outline_thread"):
            t = getattr(self, attr, None)
            if t and t.isRunning():
                try:
                    t.stop()
                    t.quit()
                    t.wait(2000)
                except Exception:
                    pass
            setattr(self, attr, None)

        super().reject()

    # ------------------ 新增审核方法 ------------------
    def _review_current_arcs(self):
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "volume":
            return
        vi = data[1]

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "审核 Agent 未配置 API Key。")
            return

        from .reviewer_agent import build_arc_review_prompt
        prompt = build_arc_review_prompt(self.working_project, vi)

        self._pending_review_task = {
            "task_type": "arcs",
            "step": "direct",  # 弧审核无需设定对齐
            "vol_idx": vi,
        }
        self.status_label.setText("AI 正在审核本卷弧结构...")
        self.review_arcs_btn.setEnabled(False)
        self.review_batch_btn.setEnabled(False)
        self.regenerate_arc_btn.setEnabled(False)
        self.batch_btn.setEnabled(False)

        self._review_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192 * 6, json_mode=True, timeout=180,
        )
        self._review_thread.finished.connect(self._on_review_finished)
        self._review_thread.error.connect(self._on_review_error)
        self._review_thread.finished.connect(self._review_thread.deleteLater)
        self._review_thread.start()

    def _review_current_batch(self):
        item = self.tree.currentItem()
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data or data[0] != "arc":
            return
        vi, ai = data[1], data[2]
        vol = self.working_project.volumes[vi]
        if not (0 <= ai < len(vol.arcs)):
            return
        arc = vol.arcs[ai]
        arc_chapters = [c for c in vol.chapters if c.arc_idx == ai]
        if not arc_chapters:
            QMessageBox.information(self, "提示", "本弧尚无章节。")
            return

        # 分批
        REVIEW_BATCH = BATCH_SIZE
        if len(arc_chapters) <= REVIEW_BATCH:
            target_chapters = arc_chapters
            batch_offset = 0
        else:
            from PyQt5.QtWidgets import QInputDialog
            options = []
            for start in range(0, len(arc_chapters), REVIEW_BATCH):
                end = min(start + REVIEW_BATCH, len(arc_chapters))
                options.append(f"第{start + 1}-{end}章")
            choice, ok = QInputDialog.getItem(
                self, "选择审核范围",
                f"本弧共 {len(arc_chapters)} 章，请选择要审核的批次：",
                options, 0, False
            )
            if not ok:
                return
            idx = options.index(choice)
            batch_offset = idx * REVIEW_BATCH
            end = min(batch_offset + REVIEW_BATCH, len(arc_chapters))
            target_chapters = arc_chapters[batch_offset:end]

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "审核 Agent 未配置 API Key。")
            return

        # Step 1：设定对齐
        self._pending_review_task = {
            "task_type": "chapters",
            "step": "align",
            "vol_idx": vi,
            "arc_idx": ai,
            "batch_offset": batch_offset,
            "batch_size": len(target_chapters),
            "target_chapters": target_chapters,
        }
        self.status_label.setText("步骤 1/2：AI 正在校验设定对齐...")
        self.review_batch_btn.setText("设定对齐中...")
        self.review_batch_btn.setEnabled(False)
        self.review_arcs_btn.setEnabled(False)
        self.regenerate_arc_btn.setEnabled(False)
        self.batch_btn.setEnabled(False)

        from .reviewer_agent import build_setting_alignment_prompt
        prompt = build_setting_alignment_prompt(
            self.working_project, vi, ai, target_chapters
        )

        self._review_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192 * 6, json_mode=True, timeout=300,
        )
        self._review_thread.finished.connect(self._on_review_finished)
        self._review_thread.error.connect(self._on_review_error)
        self._review_thread.finished.connect(self._review_thread.deleteLater)
        self._review_thread.start()

    def _on_review_finished(self, text):
        self._review_thread = None
        if self._closing:
            return

        task = self._pending_review_task
        if not task:
            return

        task_type = task.get("task_type")
        step = task.get("step")

        if task_type == "arcs":
            self._on_arcs_review_finished(text, task)
        elif task_type == "chapters":
            if step == "align":
                self._on_alignment_finished(text, task)
            elif step == "planning":
                self._on_planning_review_finished(text, task)

    def _on_alignment_finished(self, text, task):
        """设定对齐完成，进入审核和修正"""
        if self._closing:
            return

        vi = task["vol_idx"]
        ai = task["arc_idx"]
        target_chapters = task["target_chapters"]

        from reviewer_agent import parse_setting_alignment_response
        try:
            result = parse_setting_alignment_response(text)
        except Exception as e:
            if self._closing:
                return
            QMessageBox.warning(
                self, "设定对齐解析失败",
                f"对齐结果解析失败：{e}\n"
                "将跳过设定对齐，直接进入章节规划审核。"
            )
            self._continue_to_planning_review(task)
            return

        if self._closing:
            return

        has_issues = result["has_issues"]
        corrected = result["chapters"]

        applied_count = 0
        if has_issues and corrected:
            vol = self.working_project.volumes[vi]
            for item in corrected:
                if not isinstance(item, dict):
                    continue
                try:
                    ci_in_batch = int(item.get("chapter_index", -1))
                except (TypeError, ValueError):
                    continue
                if not (0 <= ci_in_batch < len(target_chapters)):
                    continue

                target_ch = target_chapters[ci_in_batch]
                plan = target_ch.plan
                if not plan:
                    continue

                new_title = (item.get("title") or "").strip()
                if new_title:
                    plan.title = new_title
                    target_ch.title = new_title

                goal = (item.get("goal") or "").strip()
                if goal:
                    plan.goal = goal

                if isinstance(item.get("characters"), list):
                    plan.characters = [
                        str(x).strip() for x in item["characters"]
                        if str(x).strip()
                    ]
                if isinstance(item.get("key_events"), list):
                    plan.key_events = [
                        str(x).strip() for x in item["key_events"]
                        if str(x).strip()
                    ]
                if isinstance(item.get("foreshadowing"), list):
                    plan.foreshadowing = [
                        str(x).strip() for x in item["foreshadowing"]
                        if str(x).strip()
                    ]

                hook = (item.get("ending_hook") or "").strip()
                if hook:
                    plan.ending_hook = hook

                try:
                    ew = int(item.get("estimated_words", 0))
                    if ew > 0:
                        plan.estimated_words = ew
                except (TypeError, ValueError):
                    pass

                applied_count += 1

            self._refresh_tree()

            if target_chapters:
                first_ch = target_chapters[0]
                vol = self.working_project.volumes[vi]
                try:
                    ci = vol.chapters.index(first_ch)
                    self._show_chapter_page(vi, ci, skip_save=True)
                except ValueError:
                    pass

        if self._closing:
            return

        if has_issues and applied_count > 0:
            QMessageBox.information(
                self, "设定对齐完成",
                f"已修正 {applied_count} 章与设定冲突的内容。\n"
                "接下来将进行章节规划审核。"
            )
        else:
            self.status_label.setText("设定对齐：无冲突")

        self._continue_to_planning_review(task)

    def _continue_to_planning_review(self, task):
        """第二步-章节规划审核"""
        if self._closing:
            return

        vi = task["vol_idx"]
        ai = task["arc_idx"]
        batch_offset = task["batch_offset"]
        target_chapters = task["target_chapters"]

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            self._reset_top_buttons()
            return

        task["step"] = "planning"
        self._pending_review_task = task

        self.status_label.setText("步骤 2/2：AI 正在审核章节规划...")
        self.review_batch_btn.setText("规划审核中...")

        from planner_agent import _build_rolling_summary
        if batch_offset == 0:
            preceding_summary = ""
            is_first_batch = True
        else:
            preceding_summary = _build_rolling_summary(
                self.working_project, vi, ai, before_count=batch_offset
            )
            is_first_batch = False

        from reviewer_agent import build_chapter_batch_review_prompt
        prompt = build_chapter_batch_review_prompt(
            self.working_project, vi, ai, target_chapters,
            preceding_summary, is_first_batch=is_first_batch
        )

        self._review_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192 * 6, json_mode=True, timeout=180,
        )
        self._review_thread.finished.connect(self._on_review_finished)
        self._review_thread.error.connect(self._on_review_error)
        self._review_thread.finished.connect(self._review_thread.deleteLater)
        self._review_thread.start()

    def _on_planning_review_finished(self, text, task):
        if self._closing:
            return

        from reviewer_agent import parse_review_response
        try:
            report = parse_review_response(text)
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"审核结果解析失败：{e}")
            self._reset_top_buttons()
            return

        from review_report_dialog import ReviewReportDialog
        dlg = ReviewReportDialog(report, parent=self)
        dlg.exec_()

        if self._closing:
            return

        if not dlg.request_revision():
            self._reset_top_buttons()
            return

        selected = dlg.get_selected_issues()
        if not selected:
            self._reset_top_buttons()
            return

        self._request_revision("chapters", task, selected)

    def _on_arcs_review_finished(self, text, task):
        """弧结构审核完成"""
        if self._closing:
            return

        from .reviewer_agent import parse_review_response
        try:
            report = parse_review_response(text)
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"审核结果解析失败：{e}")
            self._reset_top_buttons()
            return

        from .review_report_dialog import ReviewReportDialog
        dlg = ReviewReportDialog(report, parent=self)
        dlg.exec_()

        if not dlg.request_revision():
            self._reset_top_buttons()
            return

        selected = dlg.get_selected_issues()
        if not selected:
            self._reset_top_buttons()
            return

        self._request_revision("arcs", task, selected)

    def _request_revision(self, task_type, payload, issues):
        if self._review_thread and self._review_thread.isRunning():
            QMessageBox.information(self, "提示", "请等待当前任务完成。")
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "审核 Agent 未配置 API Key。")
            return

        if task_type == "arcs":
            vi = payload["vol_idx"]
            from .reviewer_agent import build_arc_revision_prompt
            prompt = build_arc_revision_prompt(self.working_project, vi, issues)
            self._pending_revision = ("arcs", payload)

        elif task_type == "chapters":
            vi = payload["vol_idx"]
            ai = payload["arc_idx"]
            batch_offset = payload.get("batch_offset", 0)
            target_chapters = payload.get("target_chapters") or []
            vol = self.working_project.volumes[vi]
            if not target_chapters:
                arc_chapters = [c for c in vol.chapters if c.arc_idx == ai]
                target = arc_chapters[batch_offset:]
            else:
                target = target_chapters
            from .reviewer_agent import build_chapter_batch_revision_prompt
            prompt = build_chapter_batch_revision_prompt(
                self.working_project, vi, ai, target, issues
            )
            self._pending_revision = ("chapters", payload)
        else:
            return

        self.status_label.setText("生成修订方案中...")
        self._review_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192 * 6, json_mode=True, timeout=180,
        )
        self._review_thread.finished.connect(self._on_revision_finished)
        self._review_thread.error.connect(self._on_revision_error)
        self._review_thread.finished.connect(self._review_thread.deleteLater)
        self._review_thread.start()

    def _on_revision_finished(self, text):
        self._review_thread = None
        if self._closing:
            return
        task = self._pending_revision
        self._pending_revision = None
        self._pending_review_task = None  # 清空两步流水线的残留状态
        self.status_label.setText("就绪")
        if not task:
            return
        task_type, payload = task

        from .reviewer_agent import (
            parse_patch_response,
            apply_arc_patches,
            apply_chapter_patches,
        )
        try:
            patches = parse_patch_response(text)
        except Exception as e:
            QMessageBox.warning(self, "解析失败", f"修订方案解析失败：{e}")
            return

        if not patches:
            QMessageBox.information(self, "无修订", "AI 未生成有效修订。")
            return

        # 应用前询问
        reply = QMessageBox.question(
            self, "确认应用",
            f"AI 生成了 {len(patches)} 条修订 patch。\n"
            "是否应用到当前工作副本？\n\n"
            "（应用后可在页面中查看，未点保存前不会影响正式项目）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        if task_type == "arcs":
            vi = payload["vol_idx"]
            vol = self.working_project.volumes[vi]
            stats = apply_arc_patches(vol, patches)
            self._refresh_tree()
            QMessageBox.information(
                self, "已应用",
                f"弧结构已更新：{stats['applied']} 条生效，{stats['skipped']} 条跳过。"
            )
        elif task_type == "chapters":
            vi = payload["vol_idx"]
            ai = payload["arc_idx"]
            batch_offset = payload.get("batch_offset", 0)
            vol = self.working_project.volumes[vi]

            # 将 chapter_index 从"批内索引"换算为"弧内索引"
            adjusted = []
            for p in patches:
                ci = p.get("chapter_index")
                if ci is None:
                    adjusted.append(p)
                    continue
                p2 = dict(p)
                try:
                    p2["chapter_index"] = int(ci) + batch_offset
                except (TypeError, ValueError):
                    p2["chapter_index"] = ci
                adjusted.append(p2)

            stats = apply_chapter_patches(vol, ai, adjusted)
            self._refresh_tree()
            QMessageBox.information(
                self, "已应用",
                f"章节规划已更新：{stats['applied']} 条生效，{stats['skipped']} 条跳过。"
            )

    def _on_revision_error(self, err):
        self._review_thread = None
        if self._closing:
            return
        self._pending_revision = None
        self._pending_review_task = None
        self.status_label.setText("就绪")
        QMessageBox.warning(self, "修订失败", err)

    def _apply_revised_arcs(self, vi, revised_arcs):
        vol = self.working_project.volumes[vi]
        from .models import StoryArc
        new_arcs = []
        for a in revised_arcs:
            if not isinstance(a, dict):
                continue
            new_arcs.append(StoryArc(
                name=(a.get("name") or "").strip(),
                goal=(a.get("goal") or "").strip(),
                estimated_chapters=int(a.get("estimated_chapters", 10) or 10),
                key_turning_points=[str(x).strip() for x in (a.get("key_turning_points") or [])],
                foreshadowing_to_plant=[str(x).strip() for x in (a.get("foreshadowing_to_plant") or [])],
                foreshadowing_to_payoff=[str(x).strip() for x in (a.get("foreshadowing_to_payoff") or [])],
            ))
        if not new_arcs:
            return
        # 校验弧数一致（避免已有章节 arc_idx 越界）
        if len(new_arcs) != len(vol.arcs):
            reply = QMessageBox.question(
                self, "确认",
                f"修订后的弧数（{len(new_arcs)}）与原弧数（{len(vol.arcs)}）不一致。\n"
                "应用后，原有章节的弧归属可能失效（落到未归属）。\n"
                "是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return
            for ch in vol.chapters:
                ch.arc_idx = -1
        vol.arcs = new_arcs
        self._refresh_tree()
        QMessageBox.information(self, "已应用", "弧结构已更新。")

    def _apply_revised_chapters(self, vi, ai, revised_chapters):
        vol = self.working_project.volumes[vi]
        # 只更新已生成章节的规划内容，不新增章节
        arc_chapters = [c for c in vol.chapters if c.arc_idx == ai]
        for i, ch in enumerate(arc_chapters):
            if i >= len(revised_chapters):
                break
            r = revised_chapters[i]
            if not isinstance(r, dict):
                continue
            old_plan = ch.plan
            new_plan = ChapterPlan(
                title=(r.get("title") or ch.title).strip(),
                goal=(r.get("goal") or "").strip(),
                characters=[str(x).strip() for x in (r.get("characters") or []) if str(x).strip()],
                key_events=[str(x).strip() for x in (r.get("key_events") or []) if str(x).strip()],
                foreshadowing=[str(x).strip() for x in (r.get("foreshadowing") or []) if str(x).strip()],
                ending_hook=(r.get("ending_hook") or "").strip(),
                estimated_words=int(r.get("estimated_words", 3000) or 3000),
                # 保留 ReAct
                detailed_outline=list(old_plan.detailed_outline) if old_plan else [],
                required_entities=dict(old_plan.required_entities) if old_plan else {},
                transition_notes=old_plan.transition_notes if old_plan else "",
                outline_thought=old_plan.outline_thought if old_plan else "",
            )
            ch.plan = new_plan
            ch.title = new_plan.title
        self._refresh_tree()
        QMessageBox.information(self, "已应用", f"本弧 {len(arc_chapters)} 章规划已更新。")

    def _on_review_error(self, err):
        self._review_thread = None
        if self._closing:
            return

        task = self._pending_review_task

        if not task:
            self._reset_top_buttons()
            self.status_label.setText(f"审核失败：{err}")
            return

        task_type = task.get("task_type")
        step = task.get("step")

        if task_type == "chapters" and step == "align":
            reply = QMessageBox.question(
                self, "设定对齐失败",
                f"设定对齐步骤出错：{err}\n\n"
                "是否跳过设定对齐，直接进入章节规划审核？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply == QMessageBox.Yes:
                self._continue_to_planning_review(task)
            else:
                self._reset_top_buttons()
            return

        self._reset_top_buttons()
        self.status_label.setText(f"审核失败：{err}")
        QMessageBox.warning(self, "审核失败", err)

    def closeEvent(self, event):
        # 标记关闭，所有回调入口会立刻返回
        self._closing = True
        self._cancelled = True

        # 清空队列，阻止新的任务启动
        self._pending_task = None
        self._pending_review_task = None
        self._pending_revision = None
        self._pending_outline_target = None

        # 停止审核线程（设定对齐 / 规划审核）
        if self._review_thread and self._review_thread.isRunning():
            try:
                self._review_thread.stop()      # 让流式循环退出
                self._review_thread.quit()
                self._review_thread.wait(2000)
            except Exception:
                pass
            self._review_thread = None

        # 停止主编排线程
        if self._thread and self._thread.isRunning():
            try:
                self._thread.stop()
                self._thread.quit()
                self._thread.wait(2000)
            except Exception:
                pass
            self._thread = None

        # 停止细纲展开线程
        if self._outline_thread and self._outline_thread.isRunning():
            try:
                self._outline_thread.stop()
                self._outline_thread.quit()
                self._outline_thread.wait(2000)
            except Exception:
                pass
            self._outline_thread = None

        super().closeEvent(event)