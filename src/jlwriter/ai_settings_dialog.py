"""
AI 助手设置：全局设置 / API 密钥 / Agent 配置
"""
from PyQt5.QtWidgets import QTabWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QComboBox, QPushButton, QMessageBox, QCheckBox, QRadioButton, QButtonGroup, QGroupBox, QWidget, QPlainTextEdit

from .ai_config import AIConfig, DEFAULT_STYLES, MODEL_PROVIDERS
from .agents import AGENT_DEFINITIONS, ResolvedAgent
from .ai_assistant import AIRequestThread

from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ui.widgets.section import HintBox


class AISettingsDialog(BaseDialog):
    def __init__(self, parent=None):
        self.config = AIConfig()
        self.config.load()
        self._test_threads = []

        super().__init__(
            parent,
            title="AI 写作助手设置",
            subtitle="配置模型供应商、API 密钥与各 Agent 的行为",
            default_size=(1500, 1000),
            min_size=(900, 620),
            show_button_bar=False,
        )

    # ============================================================
    # 内容区
    # ============================================================
    def build_content(self, layout):
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        self._setup_global_tab()
        self._setup_api_keys_tab()
        self._setup_agents_tab()

    def build_footer(self, root_layout):
        # 保存 / 取消 按钮栏
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
        save_btn.clicked.connect(self.save_settings)
        bar.addWidget(save_btn)

        root_layout.addLayout(bar)

    # ============================================================
    # 全局设置 Tab
    # ============================================================
    def _setup_global_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(SPACING.lg, SPACING.lg,
                                  SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.md)

        # 写作风格
        layout.addWidget(QLabel("写作风格："))
        style_row = QHBoxLayout()
        self.style_combo = QComboBox()
        self.style_combo.setEditable(True)
        self.style_combo.setInsertPolicy(QComboBox.NoInsert)
        all_styles = list(DEFAULT_STYLES)
        for s in self.config.custom_styles:
            if s and s not in all_styles:
                all_styles.append(s)
        self.style_combo.addItems(all_styles)
        self.style_combo.setCurrentText(self.config.style or "")
        self.style_combo.setMinimumWidth(240)
        style_row.addWidget(self.style_combo)

        self.del_style_btn = QPushButton("删除此自定义风格")
        self.del_style_btn.clicked.connect(self._delete_current_style)
        style_row.addWidget(self.del_style_btn)
        style_row.addStretch()
        layout.addLayout(style_row)

        layout.addWidget(HintBox(
            "输入新风格并保存后，会自动加入下拉列表；"
            "风格会作为 system message 的一部分注入到写作 / 精修 Agent。"
        ))

        layout.addSpacing(SPACING.lg)

        # 功能开关
        layout.addWidget(QLabel("功能开关："))

        self.enable_continue_check = QCheckBox("启用续写")
        self.enable_continue_check.setChecked(self.config.enable_continue)
        layout.addWidget(self.enable_continue_check)

        self.include_l1_rules_check = QCheckBox(
            "续写时携带完整的世界规则（L1）"
        )
        self.include_l1_rules_check.setToolTip(
            "L1 包含完整的核心设定、世界背景、力量体系与势力总览，"
            "是续写一致性的硬约束。"
        )
        self.include_l1_rules_check.setChecked(
            getattr(self.config, "include_l1_rules", True)
        )
        layout.addWidget(self.include_l1_rules_check)

        self.include_l1_outline_check = QCheckBox(
            "└─ L1 中包含故事总纲（续写单章时通常不需要）"
        )
        self.include_l1_outline_check.setChecked(
            getattr(self.config, "include_l1_outline", False)
        )
        self.include_l1_outline_check.setEnabled(
            self.include_l1_rules_check.isChecked()
        )
        self.include_l1_rules_check.toggled.connect(
            self.include_l1_outline_check.setEnabled
        )
        layout.addWidget(self.include_l1_outline_check)

        self.enable_l0_check = QCheckBox("续写时携带世界状态快照（L0）")
        self.enable_l0_check.setChecked(
            getattr(self.config, "enable_l0_world_state", False)
        )
        layout.addWidget(self.enable_l0_check)

        self.enable_outline_check = QCheckBox("启用大纲整理")
        self.enable_outline_check.setChecked(self.config.enable_outline)
        layout.addWidget(self.enable_outline_check)

        # 上下文长度
        group = QGroupBox("续写上下文长度")
        group_layout = QVBoxLayout(group)
        self.ctx_group = QButtonGroup(self)
        lengths = ["大纲", "100字", "500字", "全文", "全书"]
        current = self.config.context_length
        self._prev_ctx_button = None
        for l in lengths:
            rb = QRadioButton(l)
            if l == current:
                rb.setChecked(True)
                self._prev_ctx_button = rb
            self.ctx_group.addButton(rb)
            group_layout.addWidget(rb)
        layout.addWidget(group)
        self.ctx_group.buttonToggled.connect(self._on_ctx_button_toggled)

        layout.addStretch()
        self.tabs.addTab(tab, "全局设置")

    def _delete_current_style(self):
        style = self.style_combo.currentText().strip()
        if not style:
            return
        if style in DEFAULT_STYLES:
            QMessageBox.information(self, "提示", "预设风格不可删除。")
            return
        if style not in self.config.custom_styles:
            QMessageBox.information(
                self, "提示", "该风格尚未保存为自定义，无需删除。"
            )
            return
        reply = QMessageBox.question(self, "确认删除", f"确定删除「{style}」？")
        if reply != QMessageBox.Yes:
            return
        self.config.custom_styles.remove(style)
        idx = self.style_combo.findText(style)
        if idx >= 0:
            self.style_combo.removeItem(idx)
        self.style_combo.setCurrentText("")

    def _on_ctx_button_toggled(self, button, checked):
        if checked and button.text() == "全书":
            reply = QMessageBox.warning(
                self, "费用提示",
                "您选择了「整本书」上下文，可能产生较高的 API 调用费用。\n确定？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                if self._prev_ctx_button and self._prev_ctx_button != button:
                    self._prev_ctx_button.setChecked(True)
                else:
                    for btn in self.ctx_group.buttons():
                        if btn.text() == "500字":
                            btn.setChecked(True)
                            break
        else:
            if checked:
                self._prev_ctx_button = button

    # ============================================================
    # API 密钥 Tab
    # ============================================================
    def _setup_api_keys_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(SPACING.lg, SPACING.lg,
                                  SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.sm)

        layout.addWidget(HintBox(
            "各供应商 API 密钥按供应商分别存储，多个 Agent 共享。"
            "密钥仅保存在本机配置文件中。"
        ))

        self.key_edits = {}
        for provider, meta in MODEL_PROVIDERS.items():
            row = QHBoxLayout()
            row.setSpacing(SPACING.sm)

            label = QLabel(f"{meta['label']}:")
            label.setMinimumWidth(160)
            row.addWidget(label)

            edit = QLineEdit()
            edit.setEchoMode(QLineEdit.Password)
            edit.setText(self.config.get_api_key(provider))
            self.key_edits[provider] = edit
            row.addWidget(edit, 1)

            toggle_btn = QPushButton("👁")
            toggle_btn.setFixedWidth(40)
            toggle_btn.setCheckable(True)
            toggle_btn.setProperty("role", "ghost")

            def make_toggle(e=edit):
                def fn(checked):
                    e.setEchoMode(
                        QLineEdit.Normal if checked else QLineEdit.Password
                    )
                return fn

            toggle_btn.toggled.connect(make_toggle())
            row.addWidget(toggle_btn)
            layout.addLayout(row)

        layout.addStretch()
        self.tabs.addTab(tab, "API 密钥")

    # ============================================================
    # Agent 配置 Tab
    # ============================================================
    def _setup_agents_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(SPACING.lg, SPACING.lg,
                                  SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.md)

        # 全局写作策略
        golden_group = QGroupBox("全局写作策略")
        golden_layout = QVBoxLayout(golden_group)

        self.golden_three_check = QCheckBox(
            "启用黄金三章设计（AI 策划、章节规划、细纲展开时考虑开篇三章结构）"
        )
        self.golden_three_check.setToolTip(
            "勾选后，以下环节会被要求遵循黄金三章原则：\n"
            "· 故事总纲生成（outline 阶段）\n"
            "· 第一卷的故事弧拆解\n"
            "· 全书第 1-3 章的章节规划生成\n"
            "· 全书第 1-3 章的细纲展开"
        )
        self.golden_three_check.setChecked(
            getattr(self.config, "enable_golden_three_chapters", False)
        )
        golden_layout.addWidget(self.golden_three_check)

        golden_layout.addWidget(HintBox(
            "开启后 AI 会在开篇三章的设计上强化「抓读者」的节奏要求，"
            "适合新人作者或追求爆款开篇的项目。"
        ))
        layout.addWidget(golden_group)

        # Agent Tab
        self.agent_tabs = QTabWidget()
        self.agent_widgets = {}
        for name, defn in AGENT_DEFINITIONS.items():
            agent_tab = self._build_agent_tab(name, defn)
            self.agent_tabs.addTab(agent_tab, defn["label"])
            idx = self.agent_tabs.count() - 1
            self.agent_tabs.setTabToolTip(idx, defn.get("description", ""))
        layout.addWidget(self.agent_tabs, 1)

        self.tabs.addTab(tab, "Agent 配置")

    def _build_agent_tab(self, name, defn):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(SPACING.lg, SPACING.lg,
                                  SPACING.lg, SPACING.lg)
        layout.setSpacing(SPACING.md)
        agent = self.config.agents[name]

        # 用户说明
        user_hint = defn.get("user_hint", "") or defn.get("description", "")
        if user_hint:
            layout.addWidget(HintBox(user_hint))

        enable_check = QCheckBox("启用此 Agent")
        enable_check.setChecked(agent.enabled)
        layout.addWidget(enable_check)

        # 供应商
        prov_row = QHBoxLayout()
        prov_row.setSpacing(SPACING.md)
        prov_label = QLabel("供应商:")
        prov_label.setMinimumWidth(100)
        prov_row.addWidget(prov_label)
        prov_combo = QComboBox()
        for key, meta in MODEL_PROVIDERS.items():
            prov_combo.addItem(meta["label"], key)
        idx = prov_combo.findData(agent.provider)
        if idx >= 0:
            prov_combo.setCurrentIndex(idx)
        prov_row.addWidget(prov_combo, 1)
        layout.addLayout(prov_row)

        # 模型
        model_row = QHBoxLayout()
        model_row.setSpacing(SPACING.md)
        model_label = QLabel("模型:")
        model_label.setMinimumWidth(100)
        model_row.addWidget(model_label)
        model_combo = QComboBox()
        model_combo.setEditable(True)
        model_combo.setInsertPolicy(QComboBox.NoInsert)
        model_combo.setMinimumWidth(260)
        model_row.addWidget(model_combo, 1)
        layout.addLayout(model_row)

        # 风格开关
        use_style_check = QCheckBox("在用户指令中注入全局写作风格")
        use_style_check.setChecked(agent.use_style)
        layout.addWidget(use_style_check)

        # Persona
        layout.addWidget(QLabel("系统提示词 (System Prompt)："))
        persona_edit = QPlainTextEdit()
        persona_edit.setPlainText(agent.persona or defn["default_persona"])
        persona_edit.setMinimumHeight(180)
        layout.addWidget(persona_edit)

        test_btn = QPushButton("测试此 Agent 连接")
        layout.addWidget(test_btn)

        def refresh_model_list():
            provider_key = prov_combo.currentData()
            meta = MODEL_PROVIDERS.get(provider_key, {})
            model_combo.blockSignals(True)
            model_combo.clear()
            model_combo.addItems(meta.get("models", []))
            if agent.model and provider_key == agent.provider:
                model_combo.setCurrentText(agent.model)
            else:
                model_combo.setCurrentText(meta.get("default_model", ""))
            model_combo.blockSignals(False)

        refresh_model_list()
        prov_combo.currentIndexChanged.connect(refresh_model_list)

        def test_connection():
            provider_key = prov_combo.currentData()
            model_name = model_combo.currentText().strip()
            api_key = self.config.get_api_key(provider_key)
            if not api_key:
                QMessageBox.warning(
                    self, "提示",
                    f"尚未为 {MODEL_PROVIDERS[provider_key]['label']} "
                    f"配置 API Key，请先在「API 密钥」标签页填写。"
                )
                return

            resolved = ResolvedAgent(
                name=name,
                provider=provider_key,
                model=model_name,
                api_key=api_key,
                base_url=MODEL_PROVIDERS[provider_key].get("base_url"),
                persona=persona_edit.toPlainText() or "你是一个专业的助手",
                style="",
            )
            thread = AIRequestThread(
                resolved, "测试连接，请回复：连接成功",
                parent=self, timeout=30,
            )
            thread.finished.connect(lambda msg: QMessageBox.information(
                self, "测试结果",
                f"[{defn['label']}] 回复: {msg[:200]}"
            ))
            thread.error.connect(lambda err: QMessageBox.warning(
                self, "连接失败", f"[{defn['label']}] {err}"
            ))
            thread.finished.connect(thread.deleteLater)
            thread.error.connect(thread.deleteLater)
            thread.start()
            self._test_threads.append(thread)

        test_btn.clicked.connect(test_connection)

        self.agent_widgets[name] = {
            "enable": enable_check,
            "provider": prov_combo,
            "model": model_combo,
            "use_style": use_style_check,
            "persona": persona_edit,
        }
        return tab

    # ============================================================
    # 保存
    # ============================================================
    def save_settings(self):
        self.config.style = self.style_combo.currentText().strip()
        if (self.config.style
                and self.config.style not in DEFAULT_STYLES
                and self.config.style not in self.config.custom_styles):
            self.config.custom_styles.append(self.config.style)

        self.config.enable_continue = self.enable_continue_check.isChecked()
        self.config.enable_outline = self.enable_outline_check.isChecked()
        checked_btn = self.ctx_group.checkedButton()
        if checked_btn:
            self.config.context_length = checked_btn.text()
        self.config.include_l1_rules = self.include_l1_rules_check.isChecked()
        self.config.include_l1_outline = (
            self.include_l1_outline_check.isChecked()
        )
        self.config.enable_l0_world_state = self.enable_l0_check.isChecked()

        for provider, edit in self.key_edits.items():
            self.config.set_api_key(provider, edit.text())

        for name, w in self.agent_widgets.items():
            agent = self.config.agents[name]
            agent.enabled = w["enable"].isChecked()
            agent.provider = w["provider"].currentData()
            agent.model = w["model"].currentText().strip()
            agent.use_style = w["use_style"].isChecked()
            agent.persona = w["persona"].toPlainText()

        self.config.enable_golden_three_chapters = (
            self.golden_three_check.isChecked()
        )

        self.config.save()
        self.accept()

    def get_config(self):
        return self.config