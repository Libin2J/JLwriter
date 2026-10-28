"""
AI 对话窗口：底部面板，包含用户输入、AI 输出和功能按钮
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit,
    QPushButton, QLabel, QMessageBox, QApplication, QSizePolicy,
    QDialog
)
from PyQt5.QtGui import QTextCursor
from .ai_assistant import AIRequestThread
from .character_index import (
    select_characters_for_context,
    format_characters_for_prompt,
)
from . import knowledge_manager as km
from .ui.literary import LiteraryCloseButton

class AIChatWidget(QWidget):
    def __init__(self, ai_config, parent=None):
        super().__init__(parent)
        self.ai_config = ai_config
        self.project = None
        self.current_volume = None
        self.current_chapter = None
        self._thread = None
        self._polish_thread = None
        self._streaming_started = False
        self._polish_started = False
        self._last_draft = None
        self.editor = None       # 由 MainWindow 注入

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(6)

        # ============================================================
        # 标题栏
        # ============================================================
        title_layout = QHBoxLayout()
        title_label = QLabel("AI 对话")
        title_label.setStyleSheet("font-weight: bold;")
        title_layout.addWidget(title_label)
        title_layout.addStretch()
        self.close_btn = LiteraryCloseButton("关闭 AI 对话窗口")
        self.close_btn.clicked.connect(self.hide)
        title_layout.addWidget(self.close_btn)
        layout.addLayout(title_layout)

        # ============================================================
        # AI 输出区：输出框 + 复制按钮（同一行，按钮垂直拉伸）
        # ============================================================
        output_row = QHBoxLayout()
        output_row.setSpacing(6)

        self.output_edit = QPlainTextEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText(
            "AI 输出将显示在这里，可复制粘贴到正文..."
        )
        self.output_edit.setMinimumHeight(110)
        self.output_edit.textChanged.connect(self._update_buttons)
        output_row.addWidget(self.output_edit, 1)

        self.copy_btn = QPushButton("复制")
        self.copy_btn.setFixedWidth(64)
        self.copy_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.copy_btn.setToolTip("复制输出框全部内容到剪贴板")
        self.copy_btn.clicked.connect(self.copy_output)
        output_row.addWidget(self.copy_btn)

        layout.addLayout(output_row, 1)

        # ============================================================
        # 用户输入区：输入框 + 发送按钮（同一行，按钮垂直拉伸）
        # ============================================================
        input_row = QHBoxLayout()
        input_row.setSpacing(6)

        self.input_edit = QPlainTextEdit()
        self.input_edit.setPlaceholderText("输入你的要求，例如：续写以下内容...")
        self.input_edit.setMaximumHeight(76)
        self.input_edit.textChanged.connect(self._update_buttons)
        input_row.addWidget(self.input_edit, 1)

        self.send_btn = QPushButton("发送")
        self.send_btn.setFixedWidth(64)
        self.send_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.send_btn.setToolTip("发送自定义指令给 AI")
        self.send_btn.clicked.connect(self.send_custom)
        input_row.addWidget(self.send_btn)

        layout.addLayout(input_row)

        # ============================================================
        # 底部固定功能栏
        # ============================================================
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        self.continue_btn = QPushButton("续写当前章节")
        self.continue_btn.setToolTip(
            "基于当前章节的上下文，让 AI 续写正文"
        )
        self.continue_btn.clicked.connect(self.request_continue)
        bottom_row.addWidget(self.continue_btn)

        self.polish_btn = QPushButton("AI 精修本章")
        self.polish_btn.setToolTip(
            "调用编辑 Agent 精修当前章节正文："
            "去除 AI 味、提升文笔、保留原意。\n"
            "精修结果会显示在输出框，不会自动替换章节正文。"
        )
        self.polish_btn.clicked.connect(self.polish_current_chapter)
        self.polish_btn.setEnabled(False)
        bottom_row.addWidget(self.polish_btn)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setToolTip("清空输入框与输出框")
        self.clear_btn.clicked.connect(self.clear_all)
        bottom_row.addWidget(self.clear_btn)

        bottom_row.addStretch()
        layout.addLayout(bottom_row)

        # 初始化按钮状态
        self._update_buttons()

        self.close_btn.clicked.connect(self.hide)

    def set_editor(self, editor):
        """注入编辑器引用，用于读取章节正文"""
        self.editor = editor

    def set_context(self, project, volume, chapter):
        """由主窗口在章节切换时调用，更新当前上下文"""
        self.project = project
        self.current_volume = volume
        self.current_chapter = chapter
        self._update_buttons()

    def request_continue(self, custom_prompt=None):
        if self._is_busy():
            QMessageBox.information(self, "提示", "正在等待上一个请求完成...")
            return
        if not self.current_chapter:
            QMessageBox.information(self, "提示", "请先选择一个章节。")
            return
        if not self.ai_config.is_agent_enabled("writer"):
            QMessageBox.warning(self, "提示", "写作 Agent 已被禁用。")
            return

        # 若章节有规划但未展开细纲 → 询问是否先展开
        plan = getattr(self.current_chapter, "plan", None)
        if plan and not plan.has_detailed_outline():
            reply = QMessageBox.question(
                self, "建议展开细纲",
                "本章规划尚未展开细纲。\n"
                "直接续写可能因未加载相关实体导致设定不一致。\n\n"
                "是否先展开细纲？（推荐）",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                # 触发细纲展开
                self._trigger_detailed_outline()
                return

        context = self._get_context()
        if not context:
            QMessageBox.information(self, "提示", "没有可用的上下文。")
            return

        # === 新增：提取字数规划 ===
        plan = getattr(self.current_chapter, "plan", None)
        word_count_block = ""
        if plan and plan.estimated_words:
            ew = plan.estimated_words
            lo = int(ew * 0.85)
            hi = int(ew * 1.5)
            word_count_block = (
                f"\n\n#字数要求\n"
                f"- 本章目标字数：约 {ew} 字\n"
                f"- 建议控制在 {lo}-{hi} 字之间\n"
                f"- 超出上限意味着描写过于臃肿，低于下限意味着情节推进不足\n"
                f"- 不要为凑字数而堆砌环境描写、心理活动、排比句、"
                f"重复的情感表达；每段都必须有实质的情节推进或信息量\n"
                f"- 对话不要写无信息量的寒暄、客套、重复确认；"
                f"每句对话都应推进情节或揭示人物\n"
            )

        # 章节偏好
        preference_block = ""
        if plan:
            pref = (plan.chapter_preference or "").strip()
            if pref:
                preference_block = (
                    f"\n\n#章节偏好\n"
                    f"- 本章偏好侧重：{pref}\n"
                    f"- 正文的描写资源、节奏、场景选择应向「{pref}」倾斜\n"
                    f"- 其它元素（如日常、冲突、抒情）作为辅助，不得喧宾夺主\n"
                    f"- 若细纲与偏好存在冲突，以细纲为准，但应在细纲允许的范围内"
                    f"尽可能体现「{pref}」的侧重\n"
                )

        if self.ai_config.context_length == "大纲":
            user_prefix = f"用户指令：{custom_prompt}\n\n" if custom_prompt else ""
            prompt = (
                    user_prefix
                    + "以下是一部小说的分层上下文（L1 世界规则 / L2 场景实体 / "
                    "L3 剧情轨道 / L4 正文上下文）。\n\n"
                    "#上下文\n"
                    + context
                    + word_count_block  # ← 注入字数块
                    + preference_block  # ← 注入偏好块
                    + "\n\n#续写要求\n"
                      "- 请续写【当前章节】的正文内容，严格遵守以下规则：\n"
                      "1. 严格遵守 L1 世界骨架中的所有硬约束（核心矛盾、力量体系、势力格局）\n"
                      "2. 若上下文含【L0 故事当前状态】，以 L0 作为'故事此刻'的事实基准："
                        "角色位置、身体状态、已知秘密、物品归属、未收束情节线均以 L0 为准；"
                        "若正文与 L0 冲突，以 L0 为准\n"
                      "3. 本章只允许 L2 场景实体中列出的角色、怪物、势力、地点、物品登场；严格遵守L2的实体外貌、形体、习惯(如果有)，不得添油加醋"
                      "早已死亡的角色仅可通过对话和回忆登场\n"
                      "4. <constraint>严格按 【L3 剧情轨道】中的本章规划推进，不得私自增删情节，不得提前完成本章规划之外的内容</constraint>\n"
                      "5. <constraint>若 L3 提供了后序章节边界，本章收尾须落在边界之前，"
                      "不得提前展开后续章节的情节</constraint>\n"
                      "6. 从上下文 L4 正文的末尾续写，不得复述已写内容\n"
                      "7. 若 L4 提供的是上一章完整正文，本章开篇须与其自然衔接\n"
                      "8. 人物内心独白必须严格独立，除非明确有读心能力，否则不能被其他角色感知\n"
                      "9. 人物对话口语化，避免过度精简；文章慎用排比和否定句式，【绝对不能重复前序章节出现过的环境描写、记流水账的情况】\n"
                      "10. 除非章节规划明确要求或信息已释放，否则不能将背景等设定信息直接写在小说正文里\n"
                      "11. 【在正式写作前先思考】:先设计3份不同情节展开草稿，选择最贴合已有设定的那份展开，输出正文，不得使用AI味浓郁的句式，少用第三人称叙述\n"
                      "12. 严格遵守前序章节的设定，【不可与前序自相矛盾】，必须要有清晰的、确定的、可解释的逻辑，涉及数字的内容必须严谨，否则应重新设计本章情节\n"
                      "13. 若上下文含【章节偏好】，正文的描写资源、"
                      "节奏、场景选择应向该偏好倾斜，"
                      "其它元素（如日常、冲突、抒情）作为辅助，不得喧宾夺主\n"
                      "14. 严格遵守上方的【字数要求】，不要超出过多\n"
                      "15. 只返回续写的正文内容，不要解释、标题或大纲格式\n"
            )
        else:
            prompt = f"请续写以下内容，保持风格一致，只返回续写内容：\n{context}"

        self._send_request(prompt)

    def _trigger_detailed_outline(self):
        """从 AI 对话窗口触发细纲展开"""
        main_win = self._find_main_window()
        if main_win is None:
            QMessageBox.information(
                self, "提示",
                "请从「AI助手 → 章节规划」中打开对话框，"
                "选中本章后点击顶部的「展开本章细纲」按钮。"
            )
            return

        # 优先调用专用方法
        if hasattr(main_win, "expand_detailed_outline_for_current"):
            main_win.expand_detailed_outline_for_current()
            return

        # 退化：打开章节规划对话框并定位当前章
        if hasattr(main_win, "open_chapter_planner"):
            vol_idx, ch_idx = -1, -1
            if self.current_volume and self.current_chapter:
                try:
                    vol_idx = self.project.volumes.index(self.current_volume)
                    ch_idx = self.current_volume.chapters.index(
                        self.current_chapter
                    )
                except ValueError:
                    vol_idx, ch_idx = -1, -1

            try:
                main_win.open_chapter_planner(
                    focus_vol_idx=vol_idx, focus_ch_idx=ch_idx
                )
            except TypeError:
                main_win.open_chapter_planner()
            return

        QMessageBox.information(
            self, "提示",
            "请从「AI助手 → 章节规划」中打开对话框，"
            "选中本章后点击顶部的「展开本章细纲」按钮。"
        )

    def send_custom(self):
        """用户自定义路径，也统一用 writer"""
        if self._is_busy():
            QMessageBox.information(self, "提示", "正在等待上一个请求完成...")
            return
        custom_prompt = self.input_edit.toPlainText().strip()
        if not custom_prompt:
            return
        self._send_request(custom_prompt)

    def _get_context(self):
        """根据 ai_config.context_length 获取上下文"""
        if not self.current_chapter:
            return ""
        length = self.ai_config.context_length
        content = self.current_chapter.content

        if length == "大纲":
            return self._build_outline_context()

        if length == "全文":
            return content

        if length == "全书":
            return self._build_book_context()

        if length == "100字":
            return content[-100:] if len(content) > 100 else content
        if length == "500字":
            return content[-500:] if len(content) > 500 else content
        return content

    def _build_outline_context(self):
        """使用 L1-L0-L2-L3-L4 分层上下文；若有细纲，按细纲加载实体"""
        if not self.project or not self.current_volume or not self.current_chapter:
            return self.current_chapter.summary if self.current_chapter else ""

        try:
            cur_vi = self.project.volumes.index(self.current_volume)
            cur_ci = self.current_volume.chapters.index(self.current_chapter)
        except ValueError:
            return self.current_chapter.summary or ""

        plan = getattr(self.current_chapter, "plan", None)
        include_l1 = getattr(self.ai_config, "include_l1_rules", True)
        include_l0 = getattr(self.ai_config, "enable_l0_world_state", False)
        include_l1_outline = getattr(
            self.ai_config, "include_l1_outline", False
        )

        # 有细纲：走新流程
        if plan and plan.has_detailed_outline():
            return self._build_context_with_detailed_outline(
                self.project, cur_vi, cur_ci, plan,
                include_l1=include_l1,
                include_l0=include_l0,
                include_l1_outline=include_l1_outline,
            )

        # 无细纲：走标准 build_context
        from .context_builder import build_context
        return build_context(
            self.project, cur_vi, cur_ci,
            include_l1_rules=include_l1,
            include_l0=include_l0,
            include_l1_outline=include_l1_outline,
        )

    def _build_context_with_detailed_outline(self, project, vol_idx, ch_idx,
                                             plan, include_l1=True,
                                             include_l0=False,
                                             include_l1_outline=False):
        """基于细纲的上下文组装：L1 → L0 → L2 → L3 → L4"""
        from .context_builder import (
            build_l1_world,
            build_l0_world_state,
            build_l3_track,
            build_l4_content,
            _flatten,
            _find_pos,
        )
        from .character_index import (
            load_entities_by_names,
            format_profiles_for_prompt,
        )

        flat = _flatten(project)
        pos = _find_pos(flat, vol_idx, ch_idx)
        if pos < 0:
            return ""

        sections = []

        # L1
        if include_l1:
            l1 = build_l1_world(
                project, include_outline=include_l1_outline
            )
            if l1:
                sections.append(l1)

        # L0
        if include_l0:
            l0 = build_l0_world_state(project, vol_idx, ch_idx)
            if l0:
                sections.append(l0)

        # L2（按细纲加载）
        required = plan.required_entities or {}
        profiles, missing = load_entities_by_names(project, required)
        profiles_text = format_profiles_for_prompt(project, profiles)
        if profiles_text:
            sections.append(
                "##L2 · 本章相关实体（按细纲加载）\n" + profiles_text
            )

        # 新实体提示
        new_entities = required.get("new_entities") or []
        if new_entities:
            type_label = {
                "character": "角色",
                "location": "地点",
                "item": "物品",
                "organization": "组织",
                "monster": "怪物",
            }
            lines = ["##本章新引入的实体（尚未建档）"]
            for e in new_entities:
                if not isinstance(e, dict):
                    continue
                typ = e.get("type", "")
                label = type_label.get(typ, typ)
                name = e.get("name", "")
                desc = e.get("description", "")
                lines.append(f"· 【{label}】{name}：{desc}")
            sections.append("\n".join(lines))

        # 清单缺失提醒
        missing_all = []
        for k, names in missing.items():
            for n in names:
                missing_all.append(n)
        if missing_all:
            sections.append(
                "##清单中未建档的实体（可能在正文中作为新出现处理）\n"
                + "、".join(missing_all)
            )

        # L3
        l3 = build_l3_track(project, vol_idx, ch_idx, flat, pos)
        if l3:
            sections.append(l3)

        # L4
        l4 = build_l4_content(flat, pos)
        if l4:
            sections.append(l4)

        return "\n\n".join(sections)

    def _build_book_context(self):
        """根据全书续写， 收集故事设定、故事背景、所有章节大纲/人物/当前章节文本"""
        if not self.project:
            return self.current_chapter.content if self.current_chapter else ""

        parts = []
        self._append_project_background(parts)

        parts.append("#书目结构")
        parts.append(f"书名：《{self.project.title}》")
        for vi, vol in enumerate(self.project.volumes):
            parts.append(f"第{vi + 1}卷：{vol.title}")
            if vol.summary.strip():
                parts.append(f"  卷摘要：{vol.summary.strip()}")
            for ci, ch in enumerate(vol.chapters):
                parts.append(f"  第{ci + 1}章：{ch.title}")
                if ch.summary.strip():
                    parts.append(f"    摘要：{ch.summary.strip()}")

        if self.current_volume and self.current_chapter:
            current_vi = self.project.volumes.index(self.current_volume)
            current_ci = self.current_volume.chapters.index(self.current_chapter)
            selected_names = select_characters_for_context(
                self.project, current_vi, current_ci, lookback=3, hops=1
            )
            if selected_names:
                char_text = format_characters_for_prompt(self.project, selected_names)
                parts.append("\n##相关角色档案")
                parts.append(char_text)

            parts.append(
                f"\n当前章节：第{current_vi + 1}卷"
                f"《{self.current_volume.title}》- {self.current_chapter.title}"
            )
            parts.append("当前章节正文：")
            parts.append(self.current_chapter.content)

        return "\n".join(parts)

    def _append_project_background(self, parts, limit_bg=3000, limit_settings=4000,
                                   limit_outline=2500):
        """把核心矛盾、故事总纲、故事背景、设定集加入上下文"""
        if not self.project:
            return

        prem = (self.project.premise or "").strip()
        outline = (self.project.outline or "").strip()
        bg = (self.project.story_background or "").strip()
        st = (self.project.settings_book or "").strip()

        if prem:
            parts.append("##核心矛盾")
            parts.append(prem)
            parts.append("")

        if outline:
            if len(outline) > limit_outline:
                outline = outline[:limit_outline] + f"\n……（已截断，原文字数 {len(outline)}）"
            parts.append("##故事总纲")
            parts.append(outline)
            parts.append("")

        if not bg and not st:
            return

        parts.append("##故事背景与设定")
        if bg:
            if len(bg) > limit_bg:
                bg = bg[:limit_bg] + f"\n……（已截断，原文字数 {len(bg)}）"
            parts.append("##故事背景")
            parts.append(bg)
        if st:
            if len(st) > limit_settings:
                st = st[:limit_settings] + f"\n……（已截断，原文字数 {len(st)}）"
            parts.append("##设定集")
            parts.append(st)
        parts.append("")

    def _on_chunk(self, text):
        """接收流式增量，实时追加到输出框"""
        if not self._streaming_started:
            self.output_edit.clear()
            self._streaming_started = True
        cursor = self.output_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.output_edit.setTextCursor(cursor)
        self.output_edit.ensureCursorVisible()
        self._update_buttons()  # 新增

    def _send_request(self, prompt):
        if self._is_busy():
            QMessageBox.information(self, "提示", "正在等待上一个请求完成...")
            return

        self._streaming_started = False
        self.output_edit.setPlainText("正在请求 AI...")
        self._update_buttons()  # 新增

        resolved = self.ai_config.resolve_agent("writer")
        if not resolved or not resolved.api_key:
            self.output_edit.setPlainText(
                "错误：写作 Agent 未配置 API Key，请到设置中填写。"
            )
            self._update_buttons()
            return

        self._thread = AIRequestThread(
            resolved, prompt, parent=self, timeout=180,
        )
        self._thread.chunk.connect(self._on_chunk)
        self._thread.finished.connect(self._on_finished)
        self._thread.error.connect(self._on_error)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.start()

    def _is_busy(self):
        """检查任一 AI 线程是否在运行"""
        for attr in ("_thread", "_polish_thread"):
            t = getattr(self, attr, None)
            if t and t.isRunning():
                return True
        return False

    def _update_buttons(self):
        """统一刷新所有按钮的可用性"""
        busy = self._is_busy()

        # 续写
        writer_ok = self.ai_config.is_agent_enabled("writer")
        self.continue_btn.setEnabled(not busy and writer_ok)

        # 精修：仅看 busy 状态，内容长度在点击时检查
        enhancer_ok = self.ai_config.is_agent_enabled("enhancer")
        self.polish_btn.setEnabled(not busy)

        # 发送
        self.send_btn.setEnabled(not busy)

        # 复制
        self.copy_btn.setEnabled(bool(self.output_edit.toPlainText().strip()))

        # 清空
        has_content = (
                bool(self.output_edit.toPlainText().strip())
                or bool(self.input_edit.toPlainText().strip())
        )
        self.clear_btn.setEnabled(has_content)

    def _on_finished(self, text):
        self._thread = None
        if not self._streaming_started:
            self.output_edit.setPlainText(text)
        self._streaming_started = False
        self._update_buttons()

    def _trigger_chapter_extraction(self):
        """触发当前章节的档案提取"""
        if not self.current_chapter:
            return
        parent = self._find_main_window()
        if parent and hasattr(parent, "extract_single_chapter"):
            parent.extract_single_chapter(self.current_chapter)
        else:
            QMessageBox.information(
                self, "提示",
                "请从「AI助手 → 提取故事档案」中选择本章进行提取。"
            )

    def _show_result(self, text):
        """兼容旧调用：直接显示最终内容"""
        if not self._streaming_started:
            self.output_edit.setPlainText(text)
        self._thread = None
        self._enhance_thread = None
        self._streaming_started = False
        self._last_draft = None

    def _on_error(self, err):
        self.output_edit.setPlainText(f"请求出错：{err}")
        self._thread = None
        self._streaming_started = False
        self._last_draft = None
        self._update_buttons()

    def clear_all(self):
        self.input_edit.clear()
        self.output_edit.clear()
        self._update_buttons()

    # ============================================================
    # AI 精修
    # ============================================================
    # ============================================================
    # AI 精修当前章节
    # ============================================================
    def polish_current_chapter(self):
        """将当前章节正文交给编辑 Agent 精修（结果输出到输出框）"""
        if self._is_busy():
            QMessageBox.information(self, "提示", "正在等待上一个请求完成...")
            return

        if not self.current_chapter:
            QMessageBox.information(self, "提示", "请先选择一个章节。")
            return

        # 从编辑器读取当前章节正文（若编辑器未绑定，退回章节存储）
        content = ""
        if self.editor is not None:
            try:
                content = self.editor.toPlainText()
            except Exception:
                content = ""
        if not content:
            content = self.current_chapter.content or ""

        stripped = content.strip()

        # 内容为空检查（含空白、空行）
        if not stripped:
            QMessageBox.information(
                self, "提示",
                "当前章节内容为空，没有可精修的内容。\n"
                "请先完成本章写作。"
            )
            return

        # 内容过少检查
        if len(stripped) < 50:
            QMessageBox.information(
                self, "提示",
                f"当前章节内容不足 50 字（当前 {len(stripped)} 字）。\n"
                "内容过少，精修效果有限，请先补充正文。"
            )
            return

        # 检查 enhancer agent
        if not self.ai_config.is_agent_enabled("enhancer"):
            QMessageBox.warning(
                self, "提示",
                "编辑 Agent 已被禁用，请到 AI 设置中启用。"
            )
            return

        resolved = self.ai_config.resolve_agent("enhancer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(
                self, "提示",
                "编辑 Agent 未配置 API Key，请到 AI 设置中填写。"
            )
            return

        # 弹出知识库选择
        from .knowledge_select_dialog import KnowledgeSelectDialog
        kdlg = KnowledgeSelectDialog(self)
        if kdlg.exec_() != QDialog.Accepted:
            return
        knowledge_config = kdlg.get_result()

        knowledge_text = self._build_knowledge_text(knowledge_config)

        # 确认
        extra = ""
        if knowledge_text:
            extra = "\n已启用知识库参考，精修效果可能更贴合你的写作风格。\n"

        reply = QMessageBox.question(
            self, "确认精修",
            f"AI 将精修当前章节《{self.current_chapter.title}》的正文"
            f"（{len(stripped)} 字）。\n"
            f"{extra}\n"
            "精修结果会显示在输出框，不会自动替换章节正文；\n"
            "如需保留章节原稿，请先保存项目。\n\n"
            "是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self._last_draft = content

        polish_prompt = self._build_polish_prompt(content, knowledge_text)

        self._polish_started = False
        self.output_edit.setPlainText("正在精修当前章节...")
        self._update_buttons()

        self._polish_thread = AIRequestThread(
            resolved, polish_prompt, parent=self,
            max_tokens=8192*4, timeout=240,
        )
        self._polish_thread.chunk.connect(self._on_polish_chunk)
        self._polish_thread.finished.connect(self._on_polish_finished)
        self._polish_thread.error.connect(self._on_polish_error)
        self._polish_thread.finished.connect(self._polish_thread.deleteLater)
        self._polish_thread.start()

    def _on_polish_chunk(self, text):
        if self._closing_safe():
            return
        if not self._polish_started:
            self.output_edit.clear()
            self._polish_started = True
        cursor = self.output_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertText(text)
        self.output_edit.setTextCursor(cursor)
        self.output_edit.ensureCursorVisible()

    def _on_polish_finished(self, text):
        self._polish_thread = None
        if not self._polish_started:
            self.output_edit.setPlainText(text)
        self._polish_started = False
        self._last_draft = None
        self._update_buttons()
        # 提示用户结果在输出框，可复制后粘贴替换
        self.status_label_hint = "精修完成，请审阅输出框内容"

    def _on_polish_error(self, err):
        self._polish_thread = None
        self._polish_started = False
        # 回退到精修前的内容
        if self._last_draft:
            self.output_edit.setPlainText(self._last_draft)
        self._last_draft = None
        self._update_buttons()
        QMessageBox.warning(self, "精修失败", err)

    def _build_knowledge_text(self, config):
        """根据配置构建知识库参考文本"""
        if not config:
            return ""
        parts = []

        # AI 味模板（全部）
        if config.get("use_ai_style"):
            text = km.load_ai_style_template()
            if text:
                parts.append("##AI 味去除模板（完整参考）")
                parts.append(text)
                parts.append("")

        # 文笔模板（每个文件每节随机抽样）
        if config.get("use_style"):
            style_files = config.get("style_files") or []
            count = config.get("sample_count", 10)
            for file_name in style_files:
                samples = km.load_style_sample(file_name, per_section=count)
                if not samples:
                    continue
                display = file_name.rsplit(".", 1)[0]
                parts.append(
                    f"##文笔提升参考 · {display} "
                    f"（每节随机抽取 {count} 条）"
                )
                for section_name, lines in samples.items():
                    parts.append(f"▸ {section_name}")
                    for line in lines:
                        parts.append(f"  · {line}")
                    parts.append("")
                parts.append("")

        return "\n".join(parts).rstrip()

    def _build_polish_prompt(self, content, knowledge_text=""):
        """构建精修 prompt"""
        parts = []
        parts.append(
            "#请精修以下小说正文：\n"
            "1. 去除 AI 味：删除机械排比、对称句、空洞形容词\n"
            "2. 提升文笔：语言自然、对话口语化、叙述有节奏\n"
            "3. 保留原意与情节细节，不改变故事走向\n"
            "4. 保持人物语气与性格一致\n"
            "5. 保留段落结构，不要合并或拆分段落\n"
        )
        parts.append("")

        if knowledge_text:
            parts.append(knowledge_text)
            parts.append("")
            parts.append(
                "#参考使用说明\n"
                "上述知识库内容仅供参考：\n"
                "- AI 味去除模板展示典型的 AI 写作痕迹及其改写方式，"
                "请据此识别并消除正文中的 AI 味\n"
                "- 文笔提升参考展示人物 / 对话 / 环境描写的优秀写法，"
                "可借鉴其节奏、用词、句法，但不得直接套用或抄袭\n"
                "- 案例服务于提升，不要生搬硬套，以符合原文语境为准\n"
            )
            parts.append("")

        parts.append(
            "只输出精修后的正文，不要任何解释、标题或 markdown 标记：\n\n"
            + content
        )
        return "\n".join(parts)

    def _closing_safe(self):
        """判断当前窗口是否处于可见且未被销毁状态"""
        try:
            return not self.isVisible() and not self.isEnabled()
        except Exception:
            return True

    def copy_output(self):
        text = self.output_edit.toPlainText()
        if text:
            QApplication.clipboard().setText(text)

    def _find_main_window(self):
        """
        从当前 widget 向上查找，返回带有 open_chapter_planner 或
        expand_detailed_outline_for_current 的父窗口。
        因为 AIChatWidget 被添加进 central_widget 的布局后，
        parent() 返回的是容器而非 MainWindow。
        """
        w = self.parent()
        depth = 0
        while w is not None and depth < 10:
            if (hasattr(w, "open_chapter_planner")
                    or hasattr(w, "expand_detailed_outline_for_current")):
                return w
            w = w.parent()
            depth += 1
        # 最后尝试 window()
        win = self.window()
        if win is not None and win is not self:
            if (hasattr(win, "open_chapter_planner")
                    or hasattr(win, "expand_detailed_outline_for_current")):
                return win
        return None