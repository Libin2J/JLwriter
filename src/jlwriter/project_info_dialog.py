"""
项目信息对话框：编辑书名、核心矛盾、世界背景、力量体系、故事总纲、补充设定
"""
from PyQt5.QtWidgets import QPlainTextEdit, QTabWidget, QVBoxLayout, QWidget

from .ui.literary import Field, FramedDialog


class ProjectInfoDialog(FramedDialog):
    def __init__(self, project, parent=None, on_create=False):
        self.project = project
        self.on_create = on_create
        super().__init__(
            parent,
            title="新建故事" if on_create else "项目信息 · 设定与总纲",
            subtitle="这些设定会作为 AI 写作的长期上下文",
            seal_text="纲",
            motto="纲举目张，万象归宗",
        )
        self.resize(1300, 950)
        self.setMinimumSize(820, 620)

        self.title_field = Field("书名", hint="可留空")
        self.title_edit = self.title_field.editor
        if project.title and project.title != "未命名故事":
            self.title_edit.setText(project.title)
        self.title_edit.setPlaceholderText("在此输入书名…")
        self.add_body(self.title_field)

        self.tabs = QTabWidget()
        self._build_premise_tab()
        self._build_power_tab()
        self._build_outline_tab()
        self.add_body(self.tabs, 1)

        if on_create:
            self.add_button("稍后填写", self.reject, variant="ghost")
            self.add_button(
                "开始写作", self._on_save, variant="primary", default=True
            )
        else:
            self.add_button("取消", self.reject, variant="ghost")
            self.add_button("保存", self._on_save, variant="primary", default=True)

    # ------------------------------------------------------------------ tabs
    def _build_premise_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        self.premise_edit = QPlainTextEdit()
        self.premise_edit.setPlainText(self.project.premise or "")
        self.premise_edit.setPlaceholderText(
            "例如：\n"
            "世界面临的根本问题：修真界灵气枯竭，各大宗门为争夺残余灵脉而相互倾轧。\n"
            "主角核心目标：主角出身贫寒，欲阻止灵气枯竭带来的生灵涂炭。\n"
            "主要阻碍：宗门利益集团、隐藏的幕后黑手、自身修为不足。"
        )
        self.premise_edit.setMinimumHeight(130)
        layout.addWidget(
            Field("核心矛盾", self.premise_edit, hint="故事的核心冲突与主线张力")
        )

        self.background_edit = QPlainTextEdit()
        self.background_edit.setPlainText(self.project.story_background or "")
        self.background_edit.setPlaceholderText(
            "例如：\n"
            "时代：架空的九州大陆，仙门林立。\n"
            "社会结构：以修真宗门为统治核心，凡人依附于宗门。\n"
            "关键历史：三百年前仙魔大战，天地破碎……"
        )
        self.background_edit.setMinimumHeight(130)
        layout.addWidget(
            Field("世界背景", self.background_edit, hint="时代、社会结构、关键历史")
        )
        self.tabs.addTab(tab, "核心设定")

    def _build_power_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        self.power_edit = QPlainTextEdit()
        self.power_edit.setPlainText(self.project.power_system or "")
        self.power_edit.setPlaceholderText(
            "例如：\n"
            "体系名称：九转玄功\n"
            "等级序列：炼气 → 筑基 → 金丹 → 元婴 → 化神 → 合体 → 大乘\n"
            "核心规则：突破需对应境界丹药辅助；越级战斗会遭受反噬。\n"
            "禁忌：同境界不可吞噬对方金丹；不可逆天改命。\n"
            "专有术语：玄气、灵根、道基。"
        )
        self.power_edit.setMinimumHeight(240)
        layout.addWidget(
            Field("力量体系", self.power_edit, hint="修炼 / 魔法 / 科技体系与规则")
        )
        self.tabs.addTab(tab, "力量体系")

    def _build_outline_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setSpacing(8)

        self.outline_edit = QPlainTextEdit()
        self.outline_edit.setPlainText(self.project.outline or "")
        self.outline_edit.setPlaceholderText(
            "例如：\n"
            "第一卷《初入宗门》：主角踏入青云宗，结识同门，卷入宗门大比……\n"
            "第二卷《王朝暗涌》：主角下山历练，卷入王朝更替的暗流……"
        )
        self.outline_edit.setMinimumHeight(170)
        layout.addWidget(
            Field("故事总纲", self.outline_edit, hint="分卷结构与各卷发展脉络")
        )

        self.settings_edit = QPlainTextEdit()
        self.settings_edit.setPlainText(self.project.settings_book or "")
        self.settings_edit.setPlaceholderText(
            "此处可写入无法归入上述分类的设定，如：\n"
            "地理概览、种族分布、宗教习俗、经济体系……"
        )
        self.settings_edit.setMinimumHeight(120)
        layout.addWidget(
            Field("补充设定", self.settings_edit, hint="会作为背景信息使用")
        )
        self.tabs.addTab(tab, "总纲与补充")

    # ------------------------------------------------------------------ save
    def _on_save(self):
        title = self.title_edit.text().strip()
        if title:
            self.project.title = title
        self.project.premise = self.premise_edit.toPlainText().strip()
        self.project.story_background = self.background_edit.toPlainText()
        self.project.power_system = self.power_edit.toPlainText().strip()
        self.project.outline = self.outline_edit.toPlainText()
        self.project.settings_book = self.settings_edit.toPlainText()
        self.accept()
