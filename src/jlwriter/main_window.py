import json
import os
import re
from datetime import datetime
from PyQt5.QtWidgets import QMainWindow, QAction, QActionGroup, QToolBar, QSplitter, QCheckBox, QComboBox, QFileDialog, QMessageBox, QLabel, QInputDialog, QWidget, QVBoxLayout, QHBoxLayout, QApplication, QPushButton, QLineEdit, QFontComboBox, QSpinBox, QFrame, QDialog, QListWidget, QDialogButtonBox, QTextBrowser
from PyQt5.QtCore import Qt, QSize, QTimer, QEvent, QSettings
from PyQt5.QtGui import QTextCursor, QTextBlockFormat, QFont

from .models import StoryProject, Volume, Chapter, HistoryEntry
from .theme_manager import ThemeManager
from .ui.literary import (
    FramedDialog,
    LiteraryCloseButton,
    ThemeSwitcher,
    current_scale,
    theme_choices,
)
from .story_tree import StoryTree
from .editor_widget import EditorWidget
from .outline_editor import OutlineEditor
from .search_dialog import BookSearchDialog
from .ai_config import AIConfig
from .ai_settings_dialog import AISettingsDialog
from .floating_button import FloatingAssistantButton
# 删除：from ghost_text_handler import GhostTextHandler
from .ai_chat_widget import AIChatWidget
from .ai_assistant import AIRequestThread
from .chapter_select_dialog import ChapterSelectDialog
from .character_dialog import CharacterDialog
from .character_extractor import build_archive_extraction_prompt, parse_archive_response
from .character_index import get_characters_mentioned_in_chapter, get_locations_mentioned_in_chapter, get_organizations_mentioned_in_chapter, get_items_mentioned_in_chapter, get_monsters_mentioned_in_chapter, filter_relations_for_names
from .project_info_dialog import ProjectInfoDialog
from .planner_dialog import PlannerDialog
from .first_chapter_dialog import FirstChapterDialog
from .chapter_planner_dialog import ChapterPlannerDialog
from .plan_deviation_dialog import PlanDeviationDialog
from .world_state_dialog import WorldStateDialog
from .world_state_builder import (
    get_world_state_at,
    get_previous_world_state,
    build_world_state_prompt,
    parse_world_state_response,
    save_world_state,
)
from .export_dialog import ExportDialog
from .extraction_preview import compute_extraction_diff
from .extraction_preview_dialog import ExtractionPreviewDialog
from . import book_manager as bm
from .bookshelf_dialog import BookshelfDialog

AGREEMENT_TEXT = """
AI 写作助手 - 用户使用协议与隐私声明

最后更新日期：2026 年 6 月 22 日

请仔细阅读本协议。使用本软件提供的 AI 写作助手功能（以下简称“本功能”）即表示您已充分理解并同意本协议的全部内容。

一、功能说明
本功能通过接入 DeepSeek 、 OpenAI 等第三方 AI 服务，为您提供写作建议、大纲整理等辅助功能。

二、数据上传与隐私保护
1. 为生成建议，软件会将您当前编辑的文本（包括章节内容、大纲摘要等）传输至您选择的 AI 服务提供商。
2. 传输内容严格限于实现功能所必需的最小范围，不会上传您的完整项目文件或任何未指定的文本。
3. 软件本身不收集、存储或向其他第三方泄露您的文本数据。所有传输行为仅发生在您主动使用本功能时。
4. 尽管我们采取合理措施保护您的数据，但互联网传输存在固有风险，您应理解并承担使用 AI 服务的潜在隐私风险。

三、免责声明
1. AI 生成的内容仅供参考，不保证准确性、完整性或适用性。您应自行判断并承担采纳建议所带来的任何后果。
2. 本软件开发者对因使用本功能造成的任何直接或间接损失（包括但不限于数据丢失、隐私泄露、创作中断等）不承担法律责任。
3. 您应对自己项目内容的合法性负责，不得利用本功能生成或传输违法信息。
4. 为保证AI生成质量和设定一致性，AI助手的辅助写作功能对token的消耗偏高，如果您为此配置了价格昂贵的模型，请时刻关注您的token余量。

四、用户权利
您可以在任何时候通过「AI 助手」菜单完全关闭本功能，并可随时修改 API 密钥、服务商等设置。
如您不再希望使用，请清除 API 密钥并禁用助手开关。
本软件代码完全开源，您放心可以在原代码基础上增加和自定义自己的风格。

五、法律适用
本协议的解释与适用均受中华人民共和国法律管辖。
请勿将此软件直接用于任何性质的商业盈利活动，否则软件作者将依法保留追究权利。

如果您不同意上述条款，请选择“跳过”，AI 助手将保持禁用状态，您可以稍后在软件中重新配置。
"""

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = StoryProject()
        self.current_file_path = None
        self.current_theme = "book"
        self.dirty = False
        # 字数统计
        self._word_count_timer = QTimer(self)
        self._word_count_timer.setSingleShot(True)
        self._word_count_timer.setInterval(300)
        self._word_count_timer.timeout.connect(self._recalculate_total_word_count)

        self.setWindowTitle("JLwriter - 未命名")

        # AI 助手初始化
        self.ai_config = AIConfig()
        self.ai_config.load()
        self.ai_chat_widget = None  # 延迟到 _setup_ui 中创建
        self.ai_floating_btn = None
        # 世界状态批量生成状态
        self._ws_queue = []
        self._ws_total = 0
        self._ws_done = 0
        self._ws_cancelled = False
        self._ws_current_thread = None
        self._deviation_dlg = None

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._connect_signals()
        self.current_book_dir = None
        self._show_empty_state()
        self.load_settings()
        # 若启动时没有恢复任何项目，延迟弹出书架
        QTimer.singleShot(120, self._maybe_show_bookshelf_on_startup)

        # 自动保存定时器 (3分钟)
        self.auto_save_timer = QTimer(self)
        self.auto_save_timer.timeout.connect(self.auto_save)
        self.auto_save_timer.start(180000)

        self.editor.textChanged.connect(self.on_editor_changed)

        if self.ai_config.assistant_enabled:
            self.enable_ai_assistant()
        # AI 大纲生成状态
        self._ai_chapters_queue = []
        self._ai_total = 0
        self._ai_done = 0
        self._ai_outline_cancelled = False

        self._char_queue = []
        self._char_total = 0
        self._char_done = 0
        self._char_cancelled = False
        self._char_current_thread = None

        self.showMaximized()
        # 首次用户协议
        self.check_agreement()

    # ---------- UI 布局 ----------
    def _setup_ui(self):
        self.tree = StoryTree()
        self.editor = EditorWidget()
        self.outline = OutlineEditor()
        self.status_bar = self.statusBar()
        self.status_bar.showMessage("就绪")

        # 右下角字数计数
        self.total_word_label = QLabel("全书: 0 字")
        self.total_word_label.setProperty("role", "caption")
        self.total_word_label.setContentsMargins(8, 0, 8, 0)
        self.status_bar.addPermanentWidget(self.total_word_label)

        self.chapter_word_label = QLabel("本章: 0 字")
        self.chapter_word_label.setProperty("role", "caption")
        self.chapter_word_label.setContentsMargins(8, 0, 8, 0)
        self.status_bar.addPermanentWidget(self.chapter_word_label)

        self.right_splitter = QSplitter(Qt.Horizontal)
        self.right_splitter.addWidget(self.editor)

        self.outline_container = QWidget()
        outline_layout = QVBoxLayout(self.outline_container)
        outline_layout.setContentsMargins(0, 0, 0, 0)
        outline_layout.addWidget(self.outline)
        self.outline_container.setMinimumWidth(200)
        self.outline_container.hide()
        self.right_splitter.addWidget(self.outline_container)

        self.right_splitter.setSizes([700, 300])
        self.right_splitter.setStretchFactor(0, 1)
        self.right_splitter.setStretchFactor(1, 0)

        self.main_splitter = QSplitter(Qt.Horizontal)
        self.main_splitter.addWidget(self.tree)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setSizes([220, 980])  # 左侧220px，右侧自动填充（窗口总宽1200）
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 3)
        self.tree.setMinimumWidth(180)

        # 搜索栏（与之前相同，省略以节约空间）
        self.search_bar = QFrame()
        self.search_bar.setFrameShape(QFrame.StyledPanel)
        self.search_bar.setMaximumHeight(50)
        search_main_layout = QHBoxLayout(self.search_bar)
        search_main_layout.setContentsMargins(6, 4, 6, 4)
        search_main_layout.setSpacing(6)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("查找...")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.search_action)
        search_main_layout.addWidget(self.search_input)

        self.case_check = QCheckBox("区分大小写")
        search_main_layout.addWidget(self.case_check)

        self.scope_combo = QComboBox()
        self.scope_combo.addItems(["当前章节", "整本书"])
        search_main_layout.addWidget(self.scope_combo)

        self.search_btn = QPushButton("搜索")
        self.search_btn.clicked.connect(self.search_action)
        search_main_layout.addWidget(self.search_btn)

        self.replace_widget = QWidget()
        replace_layout = QHBoxLayout(self.replace_widget)
        replace_layout.setContentsMargins(0, 0, 0, 0)
        replace_layout.setSpacing(4)

        self.replace_input = QLineEdit()
        self.replace_input.setPlaceholderText("替换为...")
        self.replace_input.setClearButtonEnabled(True)
        self.replace_input.returnPressed.connect(self.replace_action)
        replace_layout.addWidget(self.replace_input)

        self.replace_btn = QPushButton("替换")
        self.replace_btn.clicked.connect(self.replace_action)
        replace_layout.addWidget(self.replace_btn)

        self.replace_all_btn = QPushButton("全部替换")
        self.replace_all_btn.clicked.connect(self.replace_all)
        replace_layout.addWidget(self.replace_all_btn)

        self.replace_widget.hide()
        search_main_layout.addWidget(self.replace_widget)

        close_search_btn = LiteraryCloseButton("关闭搜索栏")
        close_search_btn.clicked.connect(lambda: self.search_bar.hide())
        search_main_layout.addWidget(close_search_btn)

        self.search_bar.hide()

        # 创建 AI 对话窗口（初始隐藏）
        self.ai_chat_widget = AIChatWidget(self.ai_config, self)
        self.ai_chat_widget.set_editor(self.editor)  # 新增：注入编辑器
        self.ai_chat_widget.hide()
        self.ai_chat_widget.setFixedHeight(480)

        central_widget = QWidget()
        central_layout = QVBoxLayout(central_widget)
        central_layout.setContentsMargins(0, 0, 0, 0)
        central_layout.setSpacing(0)
        central_layout.addWidget(self.main_splitter)
        central_layout.addWidget(self.search_bar)
        central_layout.addWidget(self.ai_chat_widget)  # 新增，放在最底部
        self.setCentralWidget(central_widget)

    def _setup_menu(self):
        menubar = self.menuBar()

        file_menu = menubar.addMenu("文件")
        file_menu.addAction("新建", lambda: self.new_project(show_info=True), "Ctrl+N")
        file_menu.addAction("打开书架...", self.show_bookshelf, "Ctrl+O")
        file_menu.addAction("导入项目...", self.import_project)
        file_menu.addAction("保存", self.save_project, "Ctrl+S")
        file_menu.addAction("导出项目...", self.save_as_project, "Ctrl+Shift+S")
        file_menu.addSeparator()
        file_menu.addAction("项目信息（背景 / 设定集）...", self.edit_project_info)
        file_menu.addAction("重命名书籍", self.rename_project)
        file_menu.addAction("历史记录", self.show_history)
        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)

        edit_menu = menubar.addMenu("编辑")
        edit_menu.addAction("撤销", self.editor.undo, "Ctrl+Z")
        edit_menu.addAction("重做", self.editor.redo, "Ctrl+Y")
        edit_menu.addSeparator()
        edit_menu.addAction("查找...", self.show_search_bar, "Ctrl+F")
        edit_menu.addAction("替换...", lambda: self.show_search_bar(replace=True), "Ctrl+H")
        edit_menu.addSeparator()
        edit_menu.addAction("格式整理", self.format_current_text, "Ctrl+Shift+L")

        outline_menu = menubar.addMenu("大纲")
        outline_menu.addAction("自动生成大纲", self.auto_generate_outline)

        view_menu = menubar.addMenu("视图")
        self.show_outline_action = QAction("显示大纲面板", self, checkable=True)
        self.show_outline_action.toggled.connect(self.toggle_outline)
        view_menu.addAction(self.show_outline_action)

        # 新增：字数统计开关
        self.show_word_count_action = QAction("显示字数统计", self, checkable=True)
        self.show_word_count_action.setChecked(True)
        self.show_word_count_action.toggled.connect(self.toggle_word_count)
        view_menu.addAction(self.show_word_count_action)

        # 主题：夜读 / 护眼 / 书卷（与工具栏切换器同步）
        view_menu.addSeparator()
        theme_menu = view_menu.addMenu("主题")
        self._theme_actions = {}
        theme_group = QActionGroup(self)
        theme_group.setExclusive(True)
        for key, name, description in theme_choices():
            action = QAction(name, self, checkable=True)
            action.setData(key)
            action.setToolTip(description)
            action.triggered.connect(
                lambda _checked=False, theme_key=key: self.change_theme(theme_key)
            )
            theme_group.addAction(action)
            theme_menu.addAction(action)
            self._theme_actions[key] = action
        self._theme_actions[self.current_theme].setChecked(True)

        # 界面缩放：小屏 / 高缩放的兜底，立即生效并持久化
        view_menu.addSeparator()
        scale_menu = view_menu.addMenu("界面缩放")
        self._scale_actions = {}
        scale_group = QActionGroup(self)
        scale_group.setExclusive(True)
        current_scale_value = current_scale()
        for percent in (80, 90, 95, 100, 110):
            factor = percent / 100.0
            action = QAction(f"{percent}%", self, checkable=True)
            action.setData(factor)
            action.setToolTip(f"界面按 {percent}% 缩放（字体、留白、控件尺寸一起缩放）")
            action.triggered.connect(
                lambda _checked=False, value=factor: self.change_ui_scale(value)
            )
            scale_group.addAction(action)
            scale_menu.addAction(action)
            self._scale_actions[factor] = action
            if abs(factor - current_scale_value) < 0.001:
                action.setChecked(True)

        ai_menu = menubar.addMenu("AI助手")
        ai_menu.addAction("AI 对话", self.toggle_ai_chat)
        ai_menu.addAction("AI 策划（从零构建世界）...", self.open_planner)
        ai_menu.addAction("章节规划（大纲拆解）...", self.open_chapter_planner)
        ai_menu.addAction(
            "对比当前章节规划",
            lambda: self.compare_plan_deviation()
        )
        ai_menu.addSeparator()
        ai_menu.addAction("提取故事档案...", self.extract_characters)
        ai_menu.addAction("查看故事档案", self.show_character_dialog)
        ai_menu.addSeparator()
        ai_menu.addAction("立即整理大纲", self.ai_outline_generate)
        ai_menu.addAction("取消大纲整理", self.cancel_ai_outline)
        ai_menu.addSeparator()
        ai_menu.addAction("生成当前章世界状态...", self.generate_world_state)
        ai_menu.addAction("批量生成世界状态（全书）...", self.generate_world_states_bulk)
        ai_menu.addSeparator()
        ai_menu.addSeparator()
        ai_menu.addAction("查看最近 Prompt", self.show_prompt_viewer)
        ai_menu.addSeparator()
        ai_menu.addAction("AI设置", self.show_ai_settings)
        ai_menu.addAction("开启/关闭助手", self.toggle_ai_from_menu)

    def toggle_ai_from_menu(self):
        self.toggle_ai_assistant(not self.ai_config.assistant_enabled)

    def _setup_toolbar(self):
        toolbar = QToolBar("主工具栏")
        toolbar.setIconSize(QSize(20, 20))
        self.addToolBar(toolbar)

        toolbar.addAction("新建", lambda: self.new_project(show_info=True))
        toolbar.addAction("书架", self.show_bookshelf)
        toolbar.addAction("保存", self.save_project)
        toolbar.addAction("导出", self.open_export_dialog)
        toolbar.addSeparator()

        toolbar.addAction("添加分卷", self.add_volume)
        toolbar.addAction("添加章节", self.add_chapter)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("主题"))
        self.theme_switcher = ThemeSwitcher(self.current_theme)
        self.theme_switcher.setFixedWidth(196)
        self.theme_switcher.theme_changed.connect(self.change_theme)
        toolbar.addWidget(self.theme_switcher)

        toolbar.addSeparator()
        self.font_combo = QFontComboBox()
        self.font_combo.setEditable(False)  # 禁止输入，仅下拉选择
        self.font_combo.setFixedWidth(150)
        self.font_combo.setToolTip("编辑器字体")
        self.font_combo.setCurrentFont(self.editor.font())
        self.font_combo.currentFontChanged.connect(self.change_font)
        toolbar.addWidget(self.font_combo)

        self.font_size_spin = QSpinBox()
        self.font_size_spin.setFixedWidth(58)
        self.font_size_spin.setToolTip("编辑器字号")
        self.font_size_spin.setRange(8, 72)
        self.font_size_spin.setValue(self.editor.font().pointSize())
        self.font_size_spin.valueChanged.connect(self.change_font_size)
        toolbar.addWidget(self.font_size_spin)

        toolbar.addSeparator()
        self.outline_check = QCheckBox("显示大纲")
        self.outline_check.toggled.connect(self.on_outline_check_toggled)
        toolbar.addWidget(self.outline_check)
        #toolbar.addAction("同步大纲", self.outline.sync_to_model)
        toolbar.addAction("自动大纲", self.auto_generate_outline)

        toolbar.addSeparator()
        toolbar.addAction("AI设置", self.show_ai_settings)

    def _connect_signals(self):
        self.tree.chapterSelected.connect(self.on_tree_selected)
        self.tree.structureChanged.connect(self.on_structure_changed)  # 章节树新增
        self.editor.installEventFilter(self)  # 编辑器新增
        self.outline.outlineChanged.connect(self.on_editor_changed)     #大纲编辑页面脏状态刷新
        self.tree.chapterPlanRequested.connect(self.open_chapter_planner)   # 章节树右键连按打开章节规划页面
        self.tree.chapterDeviationRequested.connect(self.compare_plan_deviation)    #章节内容与规划对比
        self.tree.chapterExportRequested.connect(self._export_single_chapter)   #导出单章
        self.editor.textChanged.connect(self._on_editor_word_count_changed)     #字数统计

    # ============================================================
    # 书架和新建书籍功能
    # ============================================================
    def _show_empty_state(self):
        """初始化空项目状态，等待用户从书架选择"""
        self.project = StoryProject()
        self.project.history = []
        self.current_file_path = None
        self.current_book_dir = None
        self.tree.load_project(self.project)
        self.editor.clear_editor()
        self.setWindowTitle("JLwriter - 未打开项目")
        self.mark_clean()
        if self.outline_container.isVisible():
            self.outline.load_project(self.project)
        self._refresh_word_count()

    def _maybe_show_bookshelf_on_startup(self):
        if not self.current_file_path:
            self.show_bookshelf()

    def show_bookshelf(self):
        # 有未保存内容时提醒
        if self.dirty and self.current_file_path:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "当前项目有未保存的更改，是否先保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save:
                self.save_project()

        dlg = BookshelfDialog(self, allow_select=True)
        if dlg.exec_() == QDialog.Accepted:
            book_dir = dlg.get_selected_book_dir()
            if book_dir:
                self._load_book(book_dir)

    def _load_book(self, book_dir):
        project_path = bm.get_project_path(book_dir)
        if not os.path.exists(project_path):
            QMessageBox.warning(self, "错误", "书籍文件不存在。")
            return
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.project = StoryProject.from_dict(data)
            self.project.history = self._load_history_file(project_path)
            self.current_book_dir = book_dir
            self.current_file_path = project_path
            self.tree.load_project(self.project)
            self.editor.clear_editor()
            self._update_window_title()
            self.mark_clean()
            if self.outline_container.isVisible():
                self.outline.load_project(self.project)
            self._refresh_word_count()
            bm.touch_updated_at(book_dir)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"打开失败: {e}")

    def import_project(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "导入项目", "",
            "JSON 文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        book_dir, _ = bm.import_external_project(path)
        if not book_dir:
            QMessageBox.warning(self, "失败", "导入失败。")
            return
        QMessageBox.information(
            self, "导入成功",
            f"已导入到书架：{os.path.basename(book_dir)}"
        )
        self._load_book(book_dir)

    def _try_rename_book_folder(self):
        """
        退出前尝试把书籍文件夹名与书名同步。
        - 仅在 current_book_dir 有效、且文件夹名与书名不一致时执行
        - 失败不阻塞退出，只打印日志
        - 成功后更新 current_book_dir / current_file_path，
          让随后的 save_settings 写入新路径
        """
        if not getattr(self, "current_book_dir", None):
            return
        if not os.path.isdir(self.current_book_dir):
            return
        if not self.current_file_path or not os.path.exists(self.current_file_path):
            return

        current_folder = os.path.basename(self.current_book_dir)
        desired_title = (self.project.title or "").strip()
        if not desired_title:
            return

        desired_folder = bm.sanitize_folder_name(desired_title)
        if not desired_folder or desired_folder == current_folder:
            return

        book_root = bm.get_book_root()
        target_dir = os.path.join(book_root, desired_folder)

        # 若目标已存在（其他书同名），追加数字后缀
        if os.path.exists(target_dir) and (
            os.path.abspath(target_dir)
            != os.path.abspath(self.current_book_dir)
        ):
            i = 2
            while True:
                candidate = os.path.join(book_root, f"{desired_folder}_{i}")
                if not os.path.exists(candidate):
                    target_dir = candidate
                    break
                i += 1

        # 源目录必须包含 project.json
        src_project = os.path.join(self.current_book_dir, "project.json")
        if not os.path.exists(src_project):
            return

        try:
            os.rename(self.current_book_dir, target_dir)
        except Exception as e:
            print(f"重命名书籍文件夹失败（不影响退出）: {e}")
            return

        # 更新引用路径
        self.current_book_dir = target_dir
        self.current_file_path = os.path.join(target_dir, "project.json")
        # 同步 meta 中的 title（若之前未同步）
        try:
            meta = bm.load_meta(target_dir)
            meta["title"] = self.project.title
            bm.save_meta(target_dir, meta)
            bm.touch_updated_at(target_dir)
        except Exception:
            pass

    # ============================================================
    # 字数统计
    # ============================================================
    def toggle_word_count(self, visible):
        # 字数统计可视化
        self.total_word_label.setVisible(visible)
        self.chapter_word_label.setVisible(visible)
        if visible:
            self._refresh_word_count()

    def _on_editor_word_count_changed(self):
        """编辑器内容变化：立即刷新本章字数，节流刷新全书"""
        text = self.editor.toPlainText()
        self.chapter_word_label.setText(f"本章: {len(text)} 字")
        # 300ms 内不再变化才重算全书
        self._word_count_timer.start()

    def _recalculate_total_word_count(self):
        """重算全书总字数"""
        total = 0
        current_ch = self.editor.current_chapter
        current_text = self.editor.toPlainText() if current_ch else ""

        for vol in self.project.volumes:
            for ch in vol.chapters:
                if ch is current_ch:
                    # 当前章用编辑器内容（可能未保存）
                    total += len(current_text)
                else:
                    total += len(ch.content or "")
        self.total_word_label.setText(f"全书: {total} 字")

    def _refresh_word_count(self):
        """强制刷新两个字数列（章节切换、项目加载等场景调用）"""
        text = self.editor.toPlainText()
        self.chapter_word_label.setText(f"本章: {len(text)} 字")
        self._recalculate_total_word_count()

    def open_export_dialog(self):
        """打开导出对话框"""
        if not self.project.volumes:
            QMessageBox.information(
                self, "提示", "项目中尚无内容，无法导出。"
            )
            return

        # 同步编辑器中最新的正文
        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()

        # 默认卷 / 章位置
        default_vol_idx = 0
        default_ch_idx = 0
        if self.editor.current_volume and self.editor.current_chapter:
            try:
                default_vol_idx = self.project.volumes.index(
                    self.editor.current_volume
                )
                default_ch_idx = self.editor.current_volume.chapters.index(
                    self.editor.current_chapter
                )
            except ValueError:
                pass

        dlg = ExportDialog(
            self.project, self,
            default_vol_idx=default_vol_idx,
            default_ch_idx=default_ch_idx,
        )
        dlg.exec_()

    def _export_single_chapter(self, vol_idx, ch_idx):
        """从章节右键菜单触发，默认选中该章"""
        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()

        dlg = ExportDialog(
            self.project, self,
            default_vol_idx=vol_idx,
            default_ch_idx=ch_idx,
        )
        # 先切换卷/章
        dlg.volume_combo.setCurrentIndex(vol_idx)
        dlg._refresh_chapter_combo()
        if ch_idx < dlg.chapter_combo.count():
            dlg.chapter_combo.setCurrentIndex(ch_idx)
        # 最后再 setChecked，触发 toggled 完成布局刷新
        dlg.rb_chapter.setChecked(True)
        dlg.exec_()

    def edit_project_info(self):
        """世界骨架提取"""
        dlg = ProjectInfoDialog(self.project, self, on_create=False)
        if dlg.exec_() == QDialog.Accepted:
            self._update_window_title()
            self.dirty = True
            if self.current_file_path:
                self._save_to_path(self.current_file_path, silent=True)

    def rename_project(self):
        name, ok = QInputDialog.getText(
            self, "重命名项目", "请输入新书名:", text=self.project.title
        )
        if ok and name.strip():
            self.project.title = name.strip()
            self._update_window_title()
            self.dirty = True
            if self.current_file_path:
                self._save_to_path(self.current_file_path, silent=True)
                if self.current_book_dir:
                    QMessageBox.information(
                        self, "重命名成功",
                        "书名已更新。\n"
                        "书籍文件夹将在程序退出时自动同步为新书名。"
                    )
                else:
                    QMessageBox.information(
                        self, "重命名成功",
                        "书名已更新并保存。"
                    )
            else:
                QMessageBox.information(
                    self, "重命名成功",
                    "书名已更新，请记得保存项目。"
                )

    def _update_window_title(self):
        """根据当前项目标题设置窗口标题"""
        title = self.project.title if self.project.title else "未命名故事"
        self.setWindowTitle(f"JLwriter - {title}")

    def format_current_text(self):
        """整理当前章节格式：段首加四个全角空格，段落间加空行"""
        if not self.editor.current_chapter:
            QMessageBox.information(self, "提示", "请先选择并打开一个章节。")
            return

        # 获取纯文本并按段落分割（保留空段落）
        raw_text = self.editor.toPlainText()
        paragraphs = raw_text.splitlines()

        # 处理：去首尾空白，加段首缩进，段落间插入空行
        formatted_lines = []
        for para in paragraphs:
            stripped = para.strip()
            # 非空段落添加两个全角空格（四个半角空格）的缩进，清除空行以便后续对齐格式
            if stripped:
                formatted_lines.append("    " + stripped)

        # 用两个换行连接各段落（即段落间有一个空行）
        formatted_text = "\n\n".join(formatted_lines)

        # 替换编辑器内容（保留撤销点）
        cursor = self.editor.textCursor()
        cursor.beginEditBlock()
        cursor.select(QTextCursor.Document)
        cursor.insertText(formatted_text)
        cursor.endEditBlock()

        # 将光标移至文档开头
        self.editor.moveCursor(QTextCursor.Start)
        self.status_bar.showMessage("格式整理完成")

    # ---------- 历史记录 ----------
    def _get_history_path(self):
        """根据当前项目文件路径返回历史文件路径"""
        if self.current_file_path:
            return self.current_file_path + ".history.json"
        return None

    def add_history(self):
        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()
        snapshot = self.project.to_dict()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 统计信息（保持不变）
        total_chapters = 0
        total_words = 0
        for vol in self.project.volumes:
            total_chapters += len(vol.chapters)
            for ch in vol.chapters:
                total_words += len(ch.content)
        cur_vol_title = self.editor.current_volume.title if self.editor.current_volume else ""
        cur_ch_title = self.editor.current_chapter.title if self.editor.current_chapter else ""
        vol_idx = -1
        ch_idx = -1
        if self.editor.current_volume and self.editor.current_chapter:
            try:
                vol_idx = self.project.volumes.index(self.editor.current_volume)
                ch_idx = self.editor.current_volume.chapters.index(self.editor.current_chapter)
            except ValueError:
                pass

        entry = HistoryEntry(
            timestamp=timestamp,
            data=snapshot,
            chapter_count=total_chapters,
            total_word_count=total_words,
            current_volume_title=cur_vol_title,
            current_chapter_title=cur_ch_title,
            current_volume_index=vol_idx,
            current_chapter_index=ch_idx
        )
        self.project.history.insert(0, entry)
        if len(self.project.history) > 50:
            self.project.history = self.project.history[:50]
        # 立即写入历史文件（如果项目已保存）
        if self.current_file_path:
            self._save_history_file()

    def show_history(self):
        dlg = QDialog(self)
        dlg.setWindowTitle("历史记录")
        dlg.resize(600, 400)
        layout = QVBoxLayout(dlg)

        label = QLabel("选择一个历史版本进行恢复（当前未保存的更改将先自动保存到历史记录）:")
        label.setWordWrap(True)
        layout.addWidget(label)

        list_widget = QListWidget()
        for i, entry in enumerate(self.project.history):
            info = f"{entry.timestamp}"
            if entry.chapter_count:
                info += f" | {entry.chapter_count}章"
            if entry.total_word_count:
                info += f" | {entry.total_word_count}字"
            if entry.current_volume_title or entry.current_chapter_title:
                info += f" | 编辑: {entry.current_volume_title}"
                if entry.current_chapter_title:
                    info += f"-{entry.current_chapter_title}"
            list_widget.addItem(info)
        layout.addWidget(list_widget)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(dlg.accept)
        btn_box.rejected.connect(dlg.reject)
        layout.addWidget(btn_box)

        if dlg.exec_() == QDialog.Accepted:
            selected = list_widget.currentRow()
            if selected >= 0:
                reply = QMessageBox.question(
                    self, "确认恢复",
                    f"确定要恢复到该版本吗？\n{self.project.history[selected].timestamp}",
                    QMessageBox.Yes | QMessageBox.No
                )
                if reply == QMessageBox.Yes:
                    self.restore_history(selected)

    def _save_history_file(self):
        path = self._get_history_path()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump([{
                    "timestamp": h.timestamp,
                    "data": h.data,
                    "chapter_count": h.chapter_count,
                    "total_word_count": h.total_word_count,
                    "current_volume_title": h.current_volume_title,
                    "current_chapter_title": h.current_chapter_title,
                    "current_volume_index": h.current_volume_index,
                    "current_chapter_index": h.current_chapter_index
                } for h in self.project.history], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print("保存历史失败:", e)  # 可删除

    def _load_history_file(self, path):
        """从历史文件加载历史记录"""
        history_path = path + ".history.json"
        if not os.path.exists(history_path):
            return []
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                raw_list = json.load(f)
            history = []
            for item in raw_list:
                history.append(HistoryEntry(
                    timestamp=item["timestamp"],
                    data=item["data"],
                    chapter_count=item.get("chapter_count", 0),
                    total_word_count=item.get("total_word_count", 0),
                    current_volume_title=item.get("current_volume_title", ""),
                    current_chapter_title=item.get("current_chapter_title", ""),
                    current_volume_index=item.get("current_volume_index", -1),
                    current_chapter_index=item.get("current_chapter_index", -1)
                ))
            return history
        except:
            return []

    def restore_history(self, index):
        # 记录插入前的历史长度
        old_len = len(self.project.history)

        # 如果当前有未保存更改，自动保存到历史记录
        if self.dirty:
            self.add_history()

        # 如果因自动保存导致列表变长，目标索引需要偏移 1
        if len(self.project.history) > old_len:
            target_index = index + 1
        else:
            target_index = index

        if target_index >= len(self.project.history):
            QMessageBox.warning(self, "恢复失败", "历史记录索引无效")
            return

        entry = self.project.history[target_index]
        all_history = self.project.history[:]

        try:
            self.project = StoryProject.from_dict(entry.data)
            self.project.history = all_history

            self.tree.load_project(self.project)
            title = os.path.basename(self.current_file_path) if self.current_file_path else "未命名"
            self.setWindowTitle(f"故事编辑器 - {title}")
            if self.outline_container.isVisible():
                self.outline.load_project(self.project)

            vi = entry.current_volume_index
            ci = entry.current_chapter_index
            chapter_loaded = False
            if 0 <= vi < len(self.project.volumes):
                vol = self.project.volumes[vi]
                if 0 <= ci < len(vol.chapters):
                    ch = vol.chapters[ci]
                    root = self.tree.invisibleRootItem()
                    vol_item = root.child(vi)
                    if vol_item:
                        self.tree.expandItem(vol_item)
                        ch_item = vol_item.child(ci)
                        if ch_item:
                            self.tree.setCurrentItem(ch_item)
                            self.editor.load_chapter(vol, ch)
                            chapter_loaded = True

            if not chapter_loaded:
                self.editor.clear_editor()

            self.dirty = False
            self._refresh_word_count()  # 新增字数刷新
            QMessageBox.information(self, "恢复成功",
                                    "项目已恢复到所选历史版本。\n当前内容已自动保存到历史记录，可再次恢复。")
        except Exception as e:
            QMessageBox.critical(self, "恢复失败", f"无法恢复历史版本: {e}")

    # ---------- 脏状态 ----------
    def on_editor_changed(self):
        self.dirty = True

    def mark_clean(self):
        self.dirty = False

    # ---------- 自动保存 ----------
    def auto_save(self):
        if self.dirty and self.current_file_path:
            self._save_to_path(self.current_file_path, silent=True)
            self.mark_clean()

    def reset_auto_save_timer(self):
        """重置自动保存定时器"""
        self.auto_save_timer.start(180000)

    # ---------- 退出处理 ----------
    def closeEvent(self, event):
        # 关闭可能存在的偏离对比对话框
        if getattr(self, "_deviation_dlg", None) is not None:
            try:
                self._deviation_dlg._stop_all_threads()
                self._deviation_dlg.reject()
            except Exception:
                pass
            self._deviation_dlg = None

        # 取消世界状态批量生成
        self._ws_cancelled = True
        self._ws_queue.clear()
        if self._ws_current_thread and self._ws_current_thread.isRunning():
            self._ws_current_thread.quit()
            self._ws_current_thread.wait(2000)

        # 取消 AI 大纲整理
        self._ai_outline_cancelled = True
        self._ai_chapters_queue.clear()
        if hasattr(self, "_ai_current_thread") and self._ai_current_thread \
                and self._ai_current_thread.isRunning():
            self._ai_current_thread.quit()
            self._ai_current_thread.wait(2000)

        # 取消角色 / 档案提取
        self._char_cancelled = True
        self._char_queue.clear()
        if self._char_current_thread and self._char_current_thread.isRunning():
            self._char_current_thread.quit()
            self._char_current_thread.wait(2000)

        self.auto_save_timer.stop()

        # ============ 保存流程 ============
        # 1. 保存项目（可能返回是否成功、是否已记历史）
        saved, history_added = self.save_on_exit()

        # 2. 重命名书籍文件夹（更新 current_file_path）
        self._try_rename_book_folder()

        # 3. 保存用户设置（写入新路径）
        self.save_settings()

        # 4. 补充历史
        if saved and not history_added:
            try:
                self.add_history()  # 内部会写历史文件
            except Exception as e:
                print(f"退出时添加历史失败: {e}")
                # 只有 add_history 失败时才兜底
                if self.current_file_path and self.project.history:
                    self._save_history_file()
        # 5. 无保存但用户关闭时，也补写一次历史（防御性）
        elif not saved and self.current_file_path and self.project.history:
            self._save_history_file()

        event.accept()

    def save_on_exit(self):
        """
        退出时保存。
        返回 (saved, history_added)：
        - (True, True)：保存成功且已添加历史（save_as_project 路径内部已记）
        - (True, False)：保存成功但未添加历史（直接 _save_to_path 路径）
        - (False, False)：未保存或用户放弃
        """
        if not self.dirty:
            return (False, False)

        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()

        if self.current_file_path:
            self._save_to_path(self.current_file_path, silent=True)
            return (True, False)

        # 无路径：询问用户是否保存
        reply = QMessageBox.question(
            self, "未保存的更改",
            "当前项目尚未保存，是否保存？",
            QMessageBox.Save | QMessageBox.Discard
        )
        if reply == QMessageBox.Save:
            self.save_as_project()  # 内部已调用 add_history
            return (True, True)
        return (False, False)

    # ---------- 设置记忆 ----------
    def get_settings_path(self):
        return os.path.join(os.path.expanduser('~'), '.story_editor_settings.json')

    def save_settings(self):
        settings = {
            'last_project': self.current_file_path if self.current_file_path else '',
            'current_theme': self.current_theme,
            'font_family': self.font_combo.currentFont().family(),
            'font_size': self.font_size_spin.value(),
            'outline_visible': self.outline_container.isVisible(),
            'current_volume_index': -1,
            'current_chapter_index': -1
        }
        if self.editor.current_volume and self.editor.current_chapter:
            try:
                vol_idx = self.project.volumes.index(self.editor.current_volume)
                ch_idx = self.editor.current_volume.chapters.index(self.editor.current_chapter)
                settings['current_volume_index'] = vol_idx
                settings['current_chapter_index'] = ch_idx
            except ValueError:
                pass
        try:
            with open(self.get_settings_path(), 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except:
            pass

    def load_settings(self):
        path = self.get_settings_path()
        if not os.path.exists(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
        except Exception:
            return

        # 应用主题（兼容旧的深色/白色/米色/护眼绿）
        theme = settings.get('current_theme', 'book')
        key = ThemeManager.apply_theme(QApplication.instance(), theme, self)
        self.current_theme = key
        self._sync_theme_ui(key)

        # 应用字体
        font_family = settings.get('font_family')
        font_size = settings.get('font_size', 12)
        if font_family:
            self.font_combo.setCurrentFont(QFont(font_family))
        self.font_size_spin.setValue(font_size)
        self.change_font_size(font_size)

        # 先加载上次项目（确保 self.project 有效）
        last_project = settings.get('last_project', '')
        if last_project and os.path.exists(last_project):
            book_dir = os.path.dirname(last_project)
            book_root = bm.get_book_root()
            if os.path.dirname(book_dir) == book_root:
                # 正常书架项目
                self._load_book(book_dir)
            else:
                # 外部项目（旧项目或用户手动打开过的），直接加载
                try:
                    with open(last_project, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    self.project = StoryProject.from_dict(data)
                    self.project.history = self._load_history_file(last_project)
                    self.current_file_path = last_project
                    self.current_book_dir = None
                    self.tree.load_project(self.project)
                    self._update_window_title()
                    vol_idx = settings.get('current_volume_index', -1)
                    ch_idx = settings.get('current_chapter_index', -1)
                    # 原有章节定位逻辑保持不变
                    self.mark_clean()
                    self._refresh_word_count()
                except Exception:
                    pass

        # 恢复大纲可见性
        if settings.get('outline_visible', False):
            self.outline_check.setChecked(True)
            QTimer.singleShot(50, lambda: self.outline.load_project(self.project))

    # ---------- 搜索（与前版本相同，保留） ----------
    def show_search_bar(self, replace=False):
        self.search_bar.show()
        self.replace_widget.setVisible(replace)
        self.search_input.setFocus()
        self.search_input.selectAll()

    def search_action(self):
        term = self.search_input.text()
        if not term:
            return
        if self.scope_combo.currentText() == "整本书":
            self.search_entire_book(term)
        else:
            self.search_current_chapter(term)

    def search_current_chapter(self, term):
        if not self.editor.current_chapter or not self.editor.current_volume:
            QMessageBox.information(self, "提示", "请先选择一个章节。")
            return
        dlg = BookSearchDialog(self.project, term, self,
                               chapter=self.editor.current_chapter,
                               volume=self.editor.current_volume)
        dlg.jump_to.connect(self._on_chapter_search_jump)
        dlg.exec_()

    def search_entire_book(self, term):
        dlg = BookSearchDialog(self.project, term, self)
        dlg.jump_to.connect(self._on_book_search_jump)
        dlg.exec_()

    def _on_chapter_search_jump(self, vol_idx, ch_idx, term, pos):
        vol = self.project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]
        if self.editor.current_chapter != ch:
            self.editor.load_chapter(vol, ch)
            root = self.tree.invisibleRootItem()
            vol_item = root.child(vol_idx)
            if vol_item:
                self.tree.expandItem(vol_item)
                ch_item = vol_item.child(ch_idx)
                if ch_item:
                    self.tree.setCurrentItem(ch_item)
        cursor = self.editor.textCursor()
        cursor.setPosition(pos)
        cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(term))
        self.editor.setTextCursor(cursor)
        self.editor.setFocus()

    def _on_book_search_jump(self, vol_idx, ch_idx, term, pos=None):
        vol = self.project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]
        root = self.tree.invisibleRootItem()
        vol_item = root.child(vol_idx)
        if vol_item:
            self.tree.expandItem(vol_item)
            ch_item = vol_item.child(ch_idx)
            if ch_item:
                self.tree.setCurrentItem(ch_item)
        self.editor.load_chapter(vol, ch)
        self.editor.moveCursor(QTextCursor.Start)
        if pos is not None:
            cursor = self.editor.textCursor()
            cursor.setPosition(pos)
            cursor.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor, len(term))
            self.editor.setTextCursor(cursor)
        else:
            self.editor.find_text(term, False, False)
        self.editor.setFocus()

    def replace_action(self):
        term = self.search_input.text()
        repl = self.replace_input.text()
        if not term:
            return
        case_sensitive = self.case_check.isChecked()  # 复选框选中 => 区分大小写
        if self.scope_combo.currentText() == "整本书":
            self.replace_entire_book(term, repl, all_occurrences=False, case_sensitive=case_sensitive)
            return
        if not self.editor.current_chapter:
            return
        if not self.editor.replace(term, repl, case_sensitive):
            QMessageBox.information(self, "替换", "未找到匹配项。")

    def replace_all(self):
        term = self.search_input.text()
        repl = self.replace_input.text()
        if not term:
            return
        case_sensitive = self.case_check.isChecked()
        if self.scope_combo.currentText() == "整本书":
            self.replace_entire_book(term, repl, all_occurrences=True, case_sensitive=case_sensitive)
            return
        if not self.editor.current_chapter:
            return
        count = self.editor.replace_all(term, repl, case_sensitive)
        QMessageBox.information(self, "全部替换", f"替换了 {count} 处。")

    def replace_entire_book(self, term, repl, all_occurrences=False, case_sensitive=True):
        count = 0
        affected = []
        flags = 0 if case_sensitive else re.IGNORECASE
        pattern = re.compile(re.escape(term), flags)

        for vi, vol in enumerate(self.project.volumes):
            for ci, ch in enumerate(vol.chapters):
                if not pattern.search(ch.content):
                    continue
                if all_occurrences:
                    cnt = len(pattern.findall(ch.content))
                    ch.content = pattern.sub(repl, ch.content)
                    count += cnt
                    affected.append(f"第{vi + 1}卷 {vol.title} 第{ci + 1}章 {ch.title}: {cnt}处")
                else:
                    # 只替换第一处
                    new_content, n = pattern.subn(repl, ch.content, count=1)
                    if n > 0:
                        ch.content = new_content
                        count += 1
                        affected.append(f"第{vi + 1}卷 {vol.title} 第{ci + 1}章 {ch.title}: 1处")
                        break
            if not all_occurrences and count > 0:
                break

        if count == 0:
            QMessageBox.information(self, "替换", "未找到匹配项。")
        else:
            detail = "\n".join(affected)
            QMessageBox.information(self, "整书替换", f"替换了 {count} 处:\n{detail}")
            if self.editor.current_chapter:
                self.editor.load_chapter(self.editor.current_volume, self.editor.current_chapter)

    # ---------- 字体 ----------
    def change_font(self, font):
        self.editor.set_editor_font(family=font.family())

    def change_font_size(self, size):
        self.editor.set_editor_font(size=size)

    # ---------- 大纲 ----------
    def on_outline_check_toggled(self, checked):
        self.show_outline_action.blockSignals(True)
        self.show_outline_action.setChecked(checked)
        self.show_outline_action.blockSignals(False)
        self.toggle_outline(checked)

    def toggle_outline(self, visible):
        if visible:
            self.outline_container.show()
            self.outline.load_project(self.project)
        else:
            self.outline_container.hide()

    # ---------- 主题 ----------
    def change_theme(self, theme_name):
        """切换到 夜读 / 护眼 / 书卷，并持久化到全局设置。"""
        key = ThemeManager.apply_theme(
            QApplication.instance(), theme_name, self, scale=current_scale()
        )
        self.current_theme = key
        self._sync_theme_ui(key)
        try:
            QSettings("JLwriter", "JLwriter").setValue("ui/theme", key)
        except Exception:
            pass

    def _sync_theme_ui(self, key):
        """同步工具栏切换器与菜单勾选状态。"""
        switcher = getattr(self, "theme_switcher", None)
        if switcher is not None:
            switcher.set_current(key)
        actions = getattr(self, "_theme_actions", None) or {}
        action = actions.get(key)
        if action is not None and not action.isChecked():
            action.setChecked(True)

    def _sync_scale_ui(self, scale):
        actions = getattr(self, "_scale_actions", None) or {}
        for factor, action in actions.items():
            action.blockSignals(True)
            action.setChecked(abs(float(factor) - float(scale)) < 0.001)
            action.blockSignals(False)

    def change_ui_scale(self, scale):
        """界面整体缩放，写入全局设置后重建样式与字体。"""
        try:
            QSettings("JLwriter", "JLwriter").setValue("ui/scale", round(float(scale), 2))
        except Exception:
            pass
        ThemeManager.apply_theme(
            QApplication.instance(), self.current_theme, self, scale=scale
        )
        self._sync_scale_ui(current_scale())
        # 放大后已打开的对话框可能重新超出屏幕，统一再收一次
        from .ui.literary.skin import fit_dialog_to_screen

        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                fit_dialog_to_screen(widget)

    def _restore_editor_font(self):
        """全局 QSS 会改写控件字体，这里恢复用户为编辑器选择的字体。"""
        if not hasattr(self, "editor"):
            return
        family = (
            self.font_combo.currentFont().family()
            if hasattr(self, "font_combo")
            else self.editor.font().family()
        )
        size = (
            self.font_size_spin.value()
            if hasattr(self, "font_size_spin")
            else self.editor.font().pointSize()
        )
        self.editor.set_editor_font(family=family, size=size)
        if hasattr(self, "outline"):
            self.outline.set_editor_font(self.editor.font())

    # ---------- 项目操作 ----------
    def on_tree_selected(self, vol, ch):
        if ch:
            self.editor.load_chapter(vol, ch)
        else:
            self.editor.clear_editor(vol)
        # 更新 AI 对话窗口的上下文
        if self.ai_chat_widget:
            self.ai_chat_widget.set_context(self.project, vol, ch)
        # 刷新字数
        self._refresh_word_count()  # 新增

    def new_project(self, show_info=True):
        """新建项目：直接弹出书籍信息对话框，保存时创建书籍目录"""
        if self.dirty and self.current_file_path:
            reply = QMessageBox.question(
                self, "未保存的更改",
                "当前项目有未保存的更改，是否先保存？",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Save:
                self.save_project()

        if not show_info:
            return

        from .book_meta_dialog import BookMetaDialog
        dlg = BookMetaDialog(parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return

        book_dir = dlg.get_book_dir()
        if book_dir:
            self._load_book(book_dir)

    def _prompt_new_project_info(self):
        dlg = ProjectInfoDialog(self.project, self, on_create=True)
        if dlg.exec_() == QDialog.Accepted:
            self.dirty = True
            self._update_window_title()

    # 修改 open_project 方法，加载历史文件
    def open_project(self):
        """从书架打开"""
        self.show_bookshelf()

    def save_project(self):
        if not self.current_file_path:
            QMessageBox.information(
                self, "提示", "当前没有打开任何项目。"
            )
            return
        self.add_history()
        self._save_to_path(self.current_file_path)
        self.reset_auto_save_timer()


    def save_as_project(self):
        """导出当前项目到外部位置"""
        if not self.current_file_path:
            QMessageBox.information(self, "提示", "当前没有打开任何项目。")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "导出项目", "", "JSON文件 (*.json);;所有文件 (*)"
        )
        if not path:
            return
        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.project.to_dict(), f,
                          ensure_ascii=False, indent=2)
            QMessageBox.information(self, "导出成功", f"已导出到：\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))

    # 修改 save_as_project 和 _save_to_path，确保不再写入历史
    def _save_to_path(self, path, silent=False):
        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()

        # 标题兜底
        if not self.project.title or self.project.title == "未命名故事":
            if self.current_book_dir:
                meta = bm.load_meta(self.current_book_dir)
                if meta["title"]:
                    self.project.title = meta["title"]
            else:
                self.project.title = os.path.splitext(
                    os.path.basename(path)
                )[0]

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.project.to_dict(), f,
                          ensure_ascii=False, indent=2)
            self.current_file_path = path

            # 同步 meta
            if self.current_book_dir:
                meta = bm.load_meta(self.current_book_dir)
                meta["title"] = self.project.title
                bm.save_meta(self.current_book_dir, meta)
                bm.touch_updated_at(self.current_book_dir)

            self._update_window_title()
            if not silent:
                QMessageBox.information(self, "成功", "项目已保存。")
            self.mark_clean()
            self._refresh_word_count()
        except Exception as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def add_volume(self):
        name, ok = QInputDialog.getText(self, "新建分卷", "分卷名称:")
        if not (ok and name.strip()):
            return
        name = name.strip()

        self.project.volumes.append(Volume(title=name))
        new_vol_idx = len(self.project.volumes) - 1

        self.dirty = True
        # 定位到新卷（选卷而非章节，编辑器会提示"选中章节进行编辑"）
        self.tree.refresh(select_vol=new_vol_idx, select_ch=-1)

        if self.outline_container.isVisible():
            self.outline.load_project(self.project)

    def add_chapter(self):
        items = self.tree.selectedItems()
        vol_idx = None
        if items:
            data = items[0].data(0, Qt.UserRole)
            if data and data[0] == "volume":
                vol_idx = data[1]
            elif data and data[0] == "chapter":
                vol_idx = data[1]
        if vol_idx is None:
            if self.project.volumes:
                vol_idx = 0
            else:
                QMessageBox.warning(self, "提示", "请先创建一个分卷。")
                return

        name, ok = QInputDialog.getText(self, "新建章节", "章节名称:")
        if not (ok and name.strip()):
            return
        name = name.strip()

        vol = self.project.volumes[vol_idx]
        vol.chapters.append(Chapter(title=name))
        new_ch_idx = len(vol.chapters) - 1

        self.dirty = True
        # 关键：定位到新章节，触发 chapterSelected 会自动加载
        self.tree.refresh(select_vol=vol_idx, select_ch=new_ch_idx)

        if self.outline_container.isVisible():
            self.outline.load_project(self.project)

    def auto_generate_outline(self):
        if not self.project.volumes:
            QMessageBox.information(self, "提示", "项目中尚无分卷和章节。")
            return
        self.outline.auto_generate_empty_summaries()

        updated = False
        for vol in self.project.volumes:
            for ch in vol.chapters:
                if not ch.summary.strip():
                    # 生成基于内容的简单摘要
                    summary = ch.content[:100].replace('\n', ' ')
                    if len(ch.content) > 100:
                        summary += "..."
                    ch.summary = summary
                    updated = True

    def on_structure_changed(self):
        if self.outline_container.isVisible():
            self.outline.load_project(self.project)

    # ----------------------------AI助手------------------------
    def check_agreement(self):
        """首次使用弹出用户协议和隐私声明"""
        path = os.path.join(os.path.expanduser('~'), '.story_editor_agreement')
        if os.path.exists(path):
            return  # 已经同意或跳过

        dlg = AgreementDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            # 同意并配置
            with open(path, 'w') as f:
                f.write('agreed')
            self.show_ai_settings()
        else:
            # 跳过，禁用 AI 助手并保存设置
            with open(path, 'w') as f:
                f.write('skipped')
            self.ai_config.assistant_enabled = False
            self.ai_config.save()
            QMessageBox.information(self, "AI 助手已禁用",
                                    "您可以稍后通过菜单栏「AI助手」->「AI设置」重新启用。")

    def show_ai_settings(self):
        dlg = AISettingsDialog(self)
        if dlg.exec_() == QDialog.Accepted:
            self.ai_config = dlg.get_config()
            if self.ai_chat_widget:
                self.ai_chat_widget.ai_config = self.ai_config
            # 若助手总开关被关闭，同步隐藏悬浮按钮等
            if not self.ai_config.assistant_enabled and self.ai_floating_btn:
                self.toggle_ai_assistant(False)

    def toggle_ai_assistant(self, enabled):
        self.ai_config.assistant_enabled = enabled
        self.ai_config.save()
        if enabled:
            if not self.ai_floating_btn:
                self.enable_ai_assistant()
        else:
            if self.ai_floating_btn:
                self.ai_floating_btn.hide()
                self.ai_floating_btn.deleteLater()
                self.ai_floating_btn = None
            # 移除 ghost_handler 相关

    def toggle_ai_chat(self):
        """显示/隐藏底部 AI 对话窗口"""
        if self.ai_chat_widget.isVisible():
            self.ai_chat_widget.hide()
        else:
            self.ai_chat_widget.show()
            # 更新上下文
            if self.editor.current_volume and self.editor.current_chapter:
                self.ai_chat_widget.set_context(
                    self.project,
                    self.editor.current_volume,
                    self.editor.current_chapter
                )

    def enable_ai_assistant(self):
        self.ai_floating_btn = FloatingAssistantButton(self)
        self.ai_floating_btn.toggle_requested.connect(self.toggle_ai_assistant)
        self.ai_floating_btn.settings_requested.connect(self.show_ai_settings)
        self.ai_floating_btn.outline_requested.connect(self.ai_outline_generate)
        self.ai_floating_btn.chat_requested.connect(self.toggle_ai_chat)
        self.ai_floating_btn.characters_extract_requested.connect(self.extract_characters)  # 新增
        self.ai_floating_btn.characters_view_requested.connect(self.show_character_dialog)  # 新增
        self.ai_floating_btn.planner_requested.connect(self.open_planner)
        self.ai_floating_btn.deviation_requested.connect(
            lambda: self.compare_plan_deviation()
        )
        self.ai_floating_btn.update_position()
        self.ai_floating_btn.show()
        self.ai_floating_btn.prompt_viewer_requested.connect(
            self.show_prompt_viewer
        )

    def show_prompt_viewer(self):
        from .prompt_history_viewer import PromptViewerDialog
        dlg = PromptViewerDialog(self)
        dlg.exec_()

    def ai_outline_generate(self):
        """为所有空白摘要章节依次生成大纲，状态栏实时提示"""
        self._ai_chapters_queue = []
        skipped_empty = 0

        for vi, vol in enumerate(self.project.volumes):
            for ci, ch in enumerate(vol.chapters):
                # 无正文的章节直接跳过
                if not (ch.content or "").strip():
                    skipped_empty += 1
                    continue
                if not ch.summary.strip():
                    self._ai_chapters_queue.append({
                        'vol_idx': vi,  # 新增
                        'ch_idx': ci,  # 新增
                        'volume_title': vol.title,
                        'chapter_title': ch.title,
                        'content_preview': ch.content,
                        'chapter_ref': ch,
                    })

        if not self._ai_chapters_queue:
            if skipped_empty > 0:
                QMessageBox.information(
                    self, "提示",
                    f"共有 {skipped_empty} 个章节无正文内容，已全部跳过。\n"
                    "请先完成章节写作后再生成大纲。"
                )
            else:
                QMessageBox.information(self, "提示", "所有章节已有摘要")
            return

        self._ai_total = len(self._ai_chapters_queue)
        self._ai_done = 0
        self.status_bar.showMessage(
            f"AI 正在整理大纲 (0/{self._ai_total}) ..."
        )
        self._ai_process_next_chapter()

    def _ai_process_next_chapter(self):
        if self._ai_outline_cancelled:
            self.status_bar.showMessage("AI 大纲整理已取消")
            return
        if not self._ai_chapters_queue:
            self.status_bar.showMessage("所有空白章节已生成大纲，请保存项目 √")
            return

        info = self._ai_chapters_queue.pop(0)

        # 新增：兜底检查
        if not (info.get('content_preview') or "").strip():
            self._ai_done += 1
            self.status_bar.showMessage(
                f"AI 整理大纲中 ({self._ai_done}/{self._ai_total})"
            )
            self._ai_process_next_chapter()
            return

        prompt = self._build_outline_prompt(info['vol_idx'], info['ch_idx'])
        target_chapter = info['chapter_ref']

        resolved = self.ai_config.resolve_agent("outliner")
        if not resolved or not resolved.api_key:
            self.status_bar.showMessage("大纲 Agent 未配置 API Key，已跳过")
            self._ai_process_next_chapter()
            return

        thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8092*2, timeout=90,
        )
        self._ai_current_thread = thread

        def on_finished(text, thread=thread):
            if self._ai_outline_cancelled:
                self._cleanup_outline_thread(thread)
                return
            # 清理可能存在的 AI 前缀内容（如“时间：”前多余说明）
            cleaned = self._clean_outline_output(text)
            target_chapter.summary = cleaned
            self.dirty = True
            self._ai_done += 1
            self.status_bar.showMessage(f"AI 整理大纲中 ({self._ai_done}/{self._ai_total})")
            self.outline.update_chapter_summary(
                info['volume_title'], info['chapter_title'], cleaned
            )
            self._cleanup_outline_thread(thread)
            self._ai_process_next_chapter()

        def on_error(err, thread=thread, info=info):
            if self._ai_outline_cancelled:
                self._cleanup_outline_thread(thread)
                return
            QMessageBox.warning(self, "AI 错误",
                                f"处理《{info['volume_title']}》- {info['chapter_title']} 时出错：{err}")
            self._ai_done += 1
            self.status_bar.showMessage(f"AI 整理大纲中 ({self._ai_done}/{self._ai_total})")
            self._cleanup_outline_thread(thread)
            self._ai_process_next_chapter()

        thread.finished.connect(on_finished, Qt.QueuedConnection)
        thread.error.connect(on_error, Qt.QueuedConnection)
        thread.start()

    def _cleanup_outline_thread(self, thread):
        if hasattr(self, '_ai_current_thread') and self._ai_current_thread is thread:
            del self._ai_current_thread
        thread.deleteLater()

    def cancel_ai_outline(self):
        """取消正在进行的 AI 大纲整理"""
        if not self._ai_chapters_queue and not hasattr(self, '_ai_current_thread'):
            return
        self._ai_outline_cancelled = True
        self._ai_chapters_queue.clear()
        self.status_bar.showMessage("正在取消 AI 大纲整理，请等待当前请求结束...")

    # ---------- 大纲生成 prompt ----------
    def _build_background_section(self, limit_bg=3000, limit_settings=4000):
        """构建背景 + 设定集文本段，用于 AI prompt。超出限制做截断"""
        parts = []
        bg = (self.project.story_background or "").strip()
        st = (self.project.settings_book or "").strip()

        if bg:
            if len(bg) > limit_bg:
                bg = bg[:limit_bg] + f"\n……（已截断，原文字数 {len(bg)}）"
            parts.append("【故事背景】")
            parts.append(bg)

        if st:
            if len(st) > limit_settings:
                st = st[:limit_settings] + f"\n……（已截断，原文字数 {len(st)}）"
            parts.append("【设定集】")
            parts.append(st)

        if not parts:
            return ""
        return "\n".join(parts) + "\n\n"

    def _build_outline_prompt(self, vol_idx, ch_idx):
        """构建结构化大纲生成 prompt，包含前序章节大纲作为上下文"""
        vol = self.project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]

        background_section = self._build_background_section()
        prev_text = self._get_previous_outlines_text(vol_idx, ch_idx, count=3)
        context_section = ""
        if prev_text:
            context_section = f"【前序章节大纲】\n{prev_text}\n\n"

        content = ch.content.strip() if ch.content.strip() else "（本章暂无正文内容）"

        prompt = f"""你是一位专业的小说编辑，正在为长篇小说整理结构化大纲。
        {background_section} {context_section}【当前章节】
        卷：第{vol_idx + 1}卷《{vol.title}》
        章：第{ch_idx + 1}章《{ch.title}》
        正文：
        {content}
    
        请根据当前章节的正文，并参考前序大纲保持故事连贯性，生成当前章节的结构化大纲。
        严格按照以下格式输出，每个字段 1-3 句话，简洁准确：
    
        时间：
        地点：
        人物：
        故事线：
        结果：
    
        要求：
        1. 只基于【当前章节】提供的正文，不得编造未出现的情节
        2. "人物"列出本章出现的关键角色及其身份（若为新角色请说明其身份或作用）
        3. "故事线"按描述顺序概括本章的情节推进过程
        4. "结果"说明本章结束时情节推进到何处，为后续埋下什么伏笔，【必须谨慎处理，不得产生误导性信息】
        5. 保持与前序章节在时间、人物、情节上的连贯
        6. 若当前章节正文为空或过短，请基于标题和前序大纲给出合理的大纲占位
        7. 只输出上述五个字段，不要添加"第X章"标题、解释、markdown 标记或任何额外说明"""
        return prompt

    def _get_previous_outlines_text(self, vol_idx, ch_idx, count=3):
        """获取当前章节之前 N 章的大纲文本（可跨卷），用于作为生成上下文"""
        all_chapters = []
        for vi, vol in enumerate(self.project.volumes):
            for ci, ch in enumerate(vol.chapters):
                all_chapters.append((vi, ci, vol, ch))

        current_pos = None
        for i, (vi, ci, _, _) in enumerate(all_chapters):
            if vi == vol_idx and ci == ch_idx:
                current_pos = i
                break

        if current_pos is None or current_pos == 0:
            return ""

        start = max(0, current_pos - count)
        prev = all_chapters[start:current_pos]

        parts = []
        for vi, ci, vol, ch in prev:
            if ch.summary.strip():
                parts.append(f"第{vi + 1}卷 第{ci + 1}章《{ch.title}》")
                parts.append(ch.summary.strip())
                parts.append("")
        return "\n".join(parts).rstrip()

    def _clean_outline_output(self, text):
        """清理 AI 输出，去掉可能的 markdown 代码块标记或多余标题行"""
        if not text:
            return ""
        t = text.strip()
        # 去掉 ```...``` 包裹
        if t.startswith("```"):
            lines = t.splitlines()
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            t = "\n".join(lines).strip()
        # 去掉开头的章节标题行（如 "第3章 xxx"），保留字段内容
        lines = t.splitlines()
        cleaned_lines = []
        for line in lines:
            s = line.strip()
            if not s:
                cleaned_lines.append("")
                continue
            # 跳过形如 “第X章 标题” 的行
            if s.startswith("第") and ("章" in s[:6]):
                continue
            cleaned_lines.append(line)
        return "\n".join(cleaned_lines).strip()

    # ---------------- 角色画像 ----------------
    def show_character_dialog(self):
        dlg = CharacterDialog(self.project, self)
        dlg.exec_()
        # 用户可能修改了画像，标记 dirty
        self.dirty = True

    def extract_characters(self):
        if not self.project.volumes:
            QMessageBox.information(self, "提示", "项目中尚无分卷和章节。")
            return

        dlg = ChapterSelectDialog(
            self.project, self, title="选择用于提取故事档案的章节"
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        selected = dlg.get_selected_chapters()
        if not selected:
            QMessageBox.information(self, "提示", "未选择任何章节。")
            return

        # ========== 新增：过滤掉无正文的章节 ==========
        valid = []
        skipped = []
        for vi, ci in selected:
            ch = self.project.volumes[vi].chapters[ci]
            if (ch.content or "").strip():
                valid.append((vi, ci))
            else:
                skipped.append((vi, ci, ch.title))

        if not valid:
            QMessageBox.information(
                self, "提示",
                "选中的章节均无正文内容，无法提取故事档案。\n"
                "请先完成章节写作后再提取。"
            )
            return

        if skipped:
            titles = "、".join(t for _, _, t in skipped[:10])
            if len(skipped) > 10:
                titles += f" 等 {len(skipped)} 章"
            reply = QMessageBox.question(
                self, "确认",
                f"以下 {len(skipped)} 个章节没有正文，将被跳过：\n"
                f"{titles}\n\n"
                f"是否继续提取剩余 {len(valid)} 个章节？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return
        # ========== 过滤结束 ==========

        self._char_queue = list(valid)
        self._char_total = len(self._char_queue)
        self._char_done = 0
        self._char_cancelled = False
        self.status_bar.showMessage(
            f"AI 正在提取故事档案 (0/{self._char_total}) ..."
        )
        self._char_process_next()

    def _char_process_next(self):
        if self._char_cancelled:
            self.status_bar.showMessage("故事档案提取已取消")
            return
        if not self._char_queue:
            self.status_bar.showMessage(
                "故事档案提取完成，可通过「AI助手 → 查看故事档案」查看 √"
            )
            self.dirty = True
            return

        vol_idx, ch_idx = self._char_queue.pop(0)
        vol = self.project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]

        # 新增：防御性检查，无正文则跳过
        if not (ch.content or "").strip():
            self._char_done += 1
            self.status_bar.showMessage(
                f"AI 提取故事档案 ({self._char_done}/{self._char_total})"
            )
            self._char_process_next()
            return

        # 只取本章出现过的已有实体，避免 token 浪费
        relevant_chars = get_characters_mentioned_in_chapter(
            self.project, vol_idx, ch_idx
        )
        relevant_monsters = get_monsters_mentioned_in_chapter(  # 新增
            self.project, vol_idx, ch_idx
        )
        relevant_locs = get_locations_mentioned_in_chapter(
            self.project, vol_idx, ch_idx
        )
        relevant_orgs = get_organizations_mentioned_in_chapter(
            self.project, vol_idx, ch_idx
        )
        relevant_items = get_items_mentioned_in_chapter(
            self.project, vol_idx, ch_idx
        )

        # 关系过滤：两端都命中相关角色
        relevant_names = {c.name for c in relevant_chars}
        relations_text = filter_relations_for_names(self.project, relevant_names)

        prompt = build_archive_extraction_prompt(
            vol_idx, ch_idx, vol, ch,
            existing_characters=relevant_chars,
            existing_monsters=relevant_monsters,  # 新增
            existing_locations=relevant_locs,
            existing_organizations=relevant_orgs,
            existing_items=relevant_items,
            existing_relations_text=relations_text,
        )

        resolved = self.ai_config.resolve_agent("extractor")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(
                self, "提示",
                "提取 Agent 未配置 API Key，请到 AI 设置中填写。"
            )
            self._char_done += 1
            self._char_process_next()
            return

        thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*6, json_mode=True, timeout=120,
        )
        self._char_current_thread = thread

        def on_finished(text, thread=thread, vol_idx=vol_idx, ch_idx=ch_idx):
            if self._char_cancelled:
                self._cleanup_char_thread(thread)
                return
            try:
                extracted = parse_archive_response(text)
            except Exception as e:
                QMessageBox.warning(
                    self, "解析失败",
                    f"第{vol_idx + 1}卷 第{ch_idx + 1}章 的档案提取结果解析失败：{e}"
                )
                self._char_done += 1
                self.status_bar.showMessage(
                    f"AI 提取故事档案 ({self._char_done}/{self._char_total})"
                )
                self._cleanup_char_thread(thread)
                self._char_process_next()
                return

            # 计算差异
            diff = compute_extraction_diff(self.project, extracted)

            # 检查是否有可应用的内容
            has_any = any(
                (d.get("new") or d.get("supplement"))
                for d in diff.values()
            )
            if has_any:
                # 弹出预览对话框
                dlg = ExtractionPreviewDialog(
                    self.project, extracted, diff, parent=self
                )
                dlg.exec_()
                if dlg.was_applied():
                    self.dirty = True

            self._char_done += 1
            self.status_bar.showMessage(
                f"AI 提取故事档案 ({self._char_done}/{self._char_total})"
            )
            self._cleanup_char_thread(thread)
            self._char_process_next()

        def on_error(err, thread=thread, vol_idx=vol_idx, ch_idx=ch_idx):
            if self._char_cancelled:
                self._cleanup_char_thread(thread)
                return
            if "被截断" in err or "max_tokens" in err:
                self.status_bar.showMessage(f"警告：{err}")
            else:
                QMessageBox.warning(
                    self, "AI 错误",
                    f"处理第{vol_idx + 1}卷 第{ch_idx + 1}章 时出错：{err}"
                )
            self._char_done += 1
            self.status_bar.showMessage(
                f"AI 提取故事档案 ({self._char_done}/{self._char_total})"
            )
            self._cleanup_char_thread(thread)
            self._char_process_next()

        thread.finished.connect(on_finished, Qt.QueuedConnection)
        thread.error.connect(on_error, Qt.QueuedConnection)
        thread.start()

    def extract_single_chapter(self, chapter):
        """对单个章节执行档案提取（供 AI 对话窗口调用）"""
        # 找到章节位置
        for vi, vol in enumerate(self.project.volumes):
            for ci, ch in enumerate(vol.chapters):
                if ch is chapter:
                    if not (ch.content or "").strip():
                        QMessageBox.information(
                            self, "提示", "本章正文为空，无法提取。"
                        )
                        return
                    # 复用批量流程
                    self._char_queue = [(vi, ci)]
                    self._char_total = 1
                    self._char_done = 0
                    self._char_cancelled = False
                    self.status_bar.showMessage(
                        "AI 正在提取故事档案 (0/1) ..."
                    )
                    self._char_process_next()
                    return
        QMessageBox.information(self, "提示", "章节不在项目中。")

    def _cleanup_char_thread(self, thread):
        if self._char_current_thread is thread:
            self._char_current_thread = None
        thread.deleteLater()

    def cancel_character_extraction(self):
        if not self._char_queue and not self._char_current_thread:
            return
        self._char_cancelled = True
        self._char_queue.clear()
        self.status_bar.showMessage("正在取消故事档案提取，等待当前请求结束...")

    # ------------- AI 策划--------------
    def open_planner(self):
        if not self.ai_config.is_agent_enabled("planner"):
            QMessageBox.warning(self, "提示",
                                "策划 Agent 已被禁用，请到 AI 设置中启用。")
            return
        resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示",
                                "策划 Agent 未配置 API Key，请到 AI 设置中填写。")
            return

        dlg = PlannerDialog(self.project, self.ai_config, self)
        if dlg.exec_() != QDialog.Accepted:
            return

        self.dirty = True
        self.tree.load_project(self.project)
        if self.outline_container.isVisible():
            self.outline.load_project(self.project)
        self._update_window_title()
        if self.ai_chat_widget and self.ai_chat_widget.isVisible():
            if self.editor.current_volume and self.editor.current_chapter:
                self.ai_chat_widget.set_context(
                    self.project,
                    self.editor.current_volume,
                    self.editor.current_chapter,
                )

        # 落盘一次，避免中途丢失
        if self.current_file_path:
            self._save_to_path(self.current_file_path, silent=True)

        # 询问章节规划
        reply = QMessageBox.question(
            self, "下一步",
            "世界观与故事框架已写入项目。\n\n"
            "是否开始「章节规划」？\n"
            "章节规划会把每卷拆解为具体章节，明确每章的目标、出场人物、"
            "关键事件、伏笔与结尾钩子，避免写作时情节推进过快或信息释放混乱。\n\n"
            "建议进行章节规划。",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self.open_chapter_planner()

        # 再询问是否写第一章
        reply = QMessageBox.question(
            self, "下一步",
            "是否立即生成第一卷第一章的正文？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply == QMessageBox.Yes:
            self._generate_first_chapter()

    def open_chapter_planner(self, focus_vol_idx=-1, focus_ch_idx=-1):
        if not self.ai_config.is_agent_enabled("planner"):
            QMessageBox.warning(self, "提示",
                                "策划 Agent 已被禁用，请到 AI 设置中启用。")
            return
        if not (self.project.outline or self.project.story_background
                or self.project.volumes):
            QMessageBox.information(
                self, "提示",
                "当前项目尚无故事大纲、背景或分卷。\n"
                "请先通过「AI 策划」生成设定，或在「文件 → 项目信息」中填写故事总纲。"
            )
            return

        from .chapter_planner_dialog import ChapterPlannerDialog
        dlg = ChapterPlannerDialog(
            self.project, self.ai_config, self,
            focus_vol_idx=focus_vol_idx,
            focus_ch_idx=focus_ch_idx,
        )
        result = dlg.exec_()

        # 只有用户确认保存后才刷新
        if result != QDialog.Accepted:
            return

        self.dirty = True
        self.tree.load_project(self.project)
        if self.outline_container.isVisible():
            self.outline.load_project(self.project)
        if self.ai_chat_widget and self.editor.current_volume and self.editor.current_chapter:
            self.ai_chat_widget.set_context(
                self.project,
                self.editor.current_volume,
                self.editor.current_chapter,
            )
        if self.current_file_path:
            self._save_to_path(self.current_file_path, silent=True)

    def expand_detailed_outline_for_current(self):
        """从 AI 对话窗口触发：打开章节规划对话框并定位到当前章"""
        if not (self.editor.current_volume and self.editor.current_chapter):
            QMessageBox.information(self, "提示", "请先选择一个章节。")
            return
        try:
            vi = self.project.volumes.index(self.editor.current_volume)
            ci = self.editor.current_volume.chapters.index(
                self.editor.current_chapter
            )
        except ValueError:
            return
        self.open_chapter_planner(focus_vol_idx=vi, focus_ch_idx=ci)

    def _generate_first_chapter(self):
        if not self.project.volumes:
            self.project.volumes.append(Volume(title="第一卷"))
        vol = self.project.volumes[0]
        if not vol.chapters:
            vol.chapters.append(Chapter(title="第一章"))

        self.tree.load_project(self.project)

        dlg = FirstChapterDialog(self.project, self.ai_config, self)
        dlg.exec_()
        target_vol, target_ch = dlg.get_result()

        if not target_vol or not target_ch:
            return

        self.dirty = True
        self.tree.load_project(self.project)
        root = self.tree.invisibleRootItem()
        vol_item = root.child(0)
        if vol_item:
            self.tree.expandItem(vol_item)
            ch_item = vol_item.child(0)
            if ch_item:
                self.tree.setCurrentItem(ch_item)

        self.editor.load_chapter(target_vol, target_ch)
        if self.ai_chat_widget:
            self.ai_chat_widget.set_context(self.project, target_vol, target_ch)

        if self.current_file_path:
            self._save_to_path(self.current_file_path, silent=True)

        QMessageBox.information(
            self, "完成",
            f"《{target_ch.title}》已保存到正文，共 {len(target_ch.content)} 字。\n"
            "可以继续使用 AI 对话窗口续写后续章节。"
        )


    def moveEvent(self, event):
        super().moveEvent(event)
        if self.ai_floating_btn:
            self.ai_floating_btn.update_position()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.ai_floating_btn:
            self.ai_floating_btn.update_position()

    def event(self, event):
        if event.type() == QEvent.WindowActivate:
            if self.ai_floating_btn and self.ai_config.assistant_enabled:
                self.ai_floating_btn.show()
                self.ai_floating_btn.update_position()
        elif event.type() == QEvent.WindowDeactivate:
            if self.ai_floating_btn:
                # 置顶时不隐藏
                if not getattr(self.ai_floating_btn, "stay_on_top", False):
                    self.ai_floating_btn.hide()
        return super().event(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                if self.ai_floating_btn:
                    self.ai_floating_btn.hide()
            else:
                pass
        super().changeEvent(event)

    def eventFilter(self, obj, event):
        # 直接返回，不再处理 Ghost 文本
        return super().eventFilter(obj, event)

    def compare_plan_deviation(self, vol_idx=-1, ch_idx=-1):
        """对比章节规划与实际内容"""
        # 未指定时取当前编辑器章节
        if vol_idx < 0 or ch_idx < 0:
            if not self.editor.current_volume or not self.editor.current_chapter:
                QMessageBox.information(self, "提示", "请先选择一个章节。")
                return
            vol_idx = self.project.volumes.index(self.editor.current_volume)
            ch_idx = self.editor.current_volume.chapters.index(
                self.editor.current_chapter
            )

        if not (0 <= vol_idx < len(self.project.volumes)):
            return
        vol = self.project.volumes[vol_idx]
        if not (0 <= ch_idx < len(vol.chapters)):
            return
        ch = vol.chapters[ch_idx]

        # 先把编辑器中的最新内容同步到 chapter
        if (self.editor.current_volume is vol
                and self.editor.current_chapter is ch):
            ch.content = self.editor.toPlainText()

        if not ch.plan:
            QMessageBox.information(
                self, "提示",
                f"《{ch.title}》尚无章节规划，无法对比。\n"
                "请先通过「AI助手 → 章节规划」为该章添加规划。"
            )
            return
        if not ch.content.strip():
            QMessageBox.information(
                self, "提示",
                f"《{ch.title}》正文为空，无法对比。"
            )
            return

        if not self.ai_config.is_agent_enabled("extractor"):
            QMessageBox.warning(
                self, "提示",
                "提取 Agent 已被禁用，请到 AI 设置中启用。"
            )
            return

        self._deviation_dlg = PlanDeviationDialog(
            self.project, vol_idx, ch_idx, self.ai_config, self
        )
        self._deviation_dlg.exec_()
        applied = self._deviation_dlg.was_applied()
        self._deviation_dlg = None

        # 关键：应用修正后，同步到编辑器与项目
        if applied:
            self._apply_deviation_result(vol_idx, ch_idx)

    def _apply_deviation_result(self, vol_idx, ch_idx):
        """
        Dialog 已修改 chapter.content，此处负责：
        1. 若编辑器正在编辑该章，重新加载编辑器内容
        2. 标记 dirty
        3. 立即落盘（若已有文件路径）
        """
        vol = self.project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]

        # 若当前编辑器正在编辑该章节，重新加载
        if (self.editor.current_volume is vol
                and self.editor.current_chapter is ch):
            # 保存原光标位置（若在文末附近，则跳到文末；否则保持相对位置）
            old_pos = self.editor.textCursor().position()

            self.editor.load_chapter(vol, ch)
            self.editor._apply_paragraph_spacing()

            # 光标移到末尾，方便继续续写
            from PyQt5.QtGui import QTextCursor
            cursor = self.editor.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.editor.setTextCursor(cursor)
        self._refresh_word_count()  # 新增字数刷新

        # 若 AI 对话窗口打开，刷新上下文
        if self.ai_chat_widget and self.ai_chat_widget.isVisible():
            if self.editor.current_volume and self.editor.current_chapter:
                self.ai_chat_widget.set_context(
                    self.project,
                    self.editor.current_volume,
                    self.editor.current_chapter,
                )

        self.dirty = True

        # 立即落盘，避免"未保存"状态被后续操作覆盖
        if self.current_file_path:
            self._save_to_path(self.current_file_path, silent=True)

        QMessageBox.information(
            self, "已保存",
            f"《{ch.title}》修正内容已应用并保存到项目。"
        )

    def generate_world_state(self):
        """为当前章节生成世界状态"""
        if not (self.editor.current_volume and self.editor.current_chapter):
            QMessageBox.information(self, "提示", "请先选择一个章节。")
            return

        # 先把编辑器中的最新内容同步到 chapter
        self.editor.current_chapter.content = self.editor.toPlainText()

        try:
            vol_idx = self.project.volumes.index(self.editor.current_volume)
            ch_idx = self.editor.current_volume.chapters.index(
                self.editor.current_chapter
            )
        except ValueError:
            QMessageBox.information(self, "提示", "当前章节不在项目中。")
            return

        ch = self.editor.current_chapter
        if not (ch.content or "").strip():
            QMessageBox.information(
                self, "提示",
                "本章正文为空，无法生成世界状态。"
            )
            return

        # 若已有本版状态，询问是否覆盖
        existing = get_world_state_at(self.project, vol_idx, ch_idx)
        if existing:
            reply = QMessageBox.question(
                self, "确认",
                "本章已存在世界状态，重新生成会覆盖原有内容。\n"
                "是否继续？",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
            )
            if reply != QMessageBox.Yes:
                return

        dlg = WorldStateDialog(
            self.project, self.ai_config, vol_idx, ch_idx, self
        )
        dlg.exec_()

        if dlg.was_applied():
            self.dirty = True
            if self.current_file_path:
                self._save_to_path(self.current_file_path, silent=True)
                QMessageBox.information(
                    self, "完成",
                    "世界状态已生成并保存。"
                )

    def generate_world_states_bulk(self):
        """为全书所有已有正文的章节串行生成世界状态"""
        # 收集待处理章节
        targets = []
        for vi, vol in enumerate(self.project.volumes):
            for ci, ch in enumerate(vol.chapters):
                if (ch.content or "").strip():
                    targets.append((vi, ci, ch))

        if not targets:
            QMessageBox.information(
                self, "提示",
                "项目中没有任何已完成正文的章节。"
            )
            return

        # 若当前编辑器有未保存内容，先同步
        if self.editor.current_chapter:
            self.editor.current_chapter.content = self.editor.toPlainText()

        reply = QMessageBox.question(
            self, "确认批量生成",
            f"将为 {len(targets)} 个章节依次生成世界状态。\n"
            "每个章节需要一次 AI 调用，进度将显示在状态栏。\n"
            "已有状态的章节会被覆盖。\n\n"
            "是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(
                self, "提示",
                "审核 Agent 与策划 Agent 都未配置 API Key。"
            )
            return

        # 串行队列
        self._ws_queue = targets
        self._ws_total = len(targets)
        self._ws_done = 0
        self._ws_cancelled = False
        self._ws_current_thread = None

        self.status_bar.showMessage(
            f"AI 生成世界状态 (0/{self._ws_total}) ..."
        )
        self._ws_process_next()

    def _ws_process_next(self):
        if self._ws_cancelled:
            self.status_bar.showMessage("世界状态生成已取消")
            return
        if not self._ws_queue:
            self.status_bar.showMessage(
                f"世界状态生成完成 ({self._ws_done}/{self._ws_total}) √"
            )
            self.dirty = True
            if self.current_file_path:
                self._save_to_path(self.current_file_path, silent=True)
            return

        vol_idx, ch_idx, ch = self._ws_queue.pop(0)
        vol = self.project.volumes[vol_idx]

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            resolved = self.ai_config.resolve_agent("planner")
        if not resolved or not resolved.api_key:
            self._ws_done += 1
            self._ws_process_next()
            return

        prev_state = get_previous_world_state(self.project, vol_idx, ch_idx)
        prompt = build_world_state_prompt(
            self.project, vol_idx, ch_idx,
            prev_state, ch.content, ch.summary
        )

        thread = AIRequestThread(
            self, prompt, parent=self,
            max_tokens=8192*4, json_mode=True, timeout=120,
        )
        self._ws_current_thread = thread

        def on_finished(text, thread=thread, vi=vol_idx, ci=ch_idx):
            if self._ws_cancelled:
                self._ws_cleanup(thread)
                return
            try:
                state = parse_world_state_response(text, vi, ci)
                save_world_state(self.project, state)
            except Exception as e:
                QMessageBox.warning(
                    self, "解析失败",
                    f"第{vi + 1}卷 第{ci + 1}章 世界状态解析失败：{e}"
                )
            self._ws_done += 1
            self.status_bar.showMessage(
                f"AI 生成世界状态 ({self._ws_done}/{self._ws_total})"
            )
            self._ws_cleanup(thread)
            self._ws_process_next()

        def on_error(err, thread=thread, vi=vol_idx, ci=ch_idx):
            if self._ws_cancelled:
                self._ws_cleanup(thread)
                return
            if "被截断" not in err and "max_tokens" not in err:
                QMessageBox.warning(
                    self, "AI 错误",
                    f"第{vi + 1}卷 第{ci + 1}章 生成失败：{err}"
                )
            self._ws_done += 1
            self.status_bar.showMessage(
                f"AI 生成世界状态 ({self._ws_done}/{self._ws_total})"
            )
            self._ws_cleanup(thread)
            self._ws_process_next()

        thread.finished.connect(on_finished, Qt.QueuedConnection)
        thread.error.connect(on_error, Qt.QueuedConnection)
        thread.start()

    def _ws_cleanup(self, thread):
        if self._ws_current_thread is thread:
            self._ws_current_thread = None
        thread.deleteLater()

    def cancel_world_state_generation(self):
        if not self._ws_queue and not self._ws_current_thread:
            return
        self._ws_cancelled = True
        self._ws_queue.clear()
        self.status_bar.showMessage("正在取消世界状态生成，等待当前请求结束...")

class AgreementDialog(FramedDialog):
    """用户协议与隐私声明：可阅读的文书版式。"""

    def __init__(self, parent=None):
        super().__init__(
            parent,
            title="AI 写作助手 · 用户协议与隐私声明",
            subtitle="启用前，请阅读以下约定",
            seal_text="契",
            motto="言而有信，落笔为凭",
        )
        self.resize(900, 760)
        self.setMinimumSize(560, 460)

        body = "\n".join(AGREEMENT_TEXT.splitlines()[2:]).strip()
        browser = QTextBrowser()
        browser.setObjectName("reader")
        browser.setOpenExternalLinks(True)
        browser.setPlainText(body)
        frame = QTextBlockFormat()
        frame.setLineHeight(165, QTextBlockFormat.ProportionalHeight)
        frame.setTopMargin(2)
        frame.setBottomMargin(4)
        cursor = QTextCursor(browser.document())
        cursor.select(QTextCursor.Document)
        cursor.mergeBlockFormat(frame)
        self.add_body(browser, 1)

        self.add_button("跳过（稍后设置）", self.reject, variant="ghost")
        self.add_button(
            "同意并配置 AI 助手", self.accept, variant="primary", default=True
        )