"""文学风 UI 设计系统的离线测试（不依赖主窗口业务数据）。"""
from __future__ import annotations

import importlib
import os
import unittest
from pathlib import Path

os.environ.setdefault(
    "JLWRITER_DATA_DIR", str(Path(__file__).resolve().parent / "_tmp" / "ui_data")
)

from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

APP = QApplication.instance() or QApplication([])

from jlwriter.ui.literary import (  # noqa: E402
    DEFAULT_THEME,
    PALETTES,
    Field,
    FramedDialog,
    LiteraryButton,
    LiteraryDialog,
    ThemeSwitcher,
    ToggleSwitch,
    apply_theme,
    current_palette,
    current_theme,
    normalize_theme,
)
from jlwriter.ui.literary.skin import polish_dialog  # noqa: E402
from jlwriter.ui.literary.themes import get_palette  # noqa: E402
from jlwriter.ui.literary.widgets import DialogHeader  # noqa: E402


def _luminance(hex_color: str) -> float:
    hex_color = hex_color.lstrip("#")
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (0, 2, 4)]
    linear = [
        value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4
        for value in channels
    ]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    lighter, darker = max(la, lb), min(la, lb)
    return (lighter + 0.05) / (darker + 0.05)


class ThemeTests(unittest.TestCase):
    def tearDown(self) -> None:
        apply_theme(APP, DEFAULT_THEME)

    def test_three_themes_exist_and_are_distinct(self):
        self.assertEqual(set(PALETTES), {"night", "eye", "book"})
        canvases = {palette.canvas for palette in PALETTES.values()}
        accents = {palette.accent for palette in PALETTES.values()}
        self.assertEqual(len(canvases), 3)
        self.assertEqual(len(accents), 3)

    def test_every_theme_has_readable_contrast(self):
        for palette in PALETTES.values():
            self.assertGreaterEqual(
                _contrast(palette.ink, palette.canvas),
                7.0,
                msg=f"{palette.name} 正文对比度不足",
            )
            self.assertGreaterEqual(
                _contrast(palette.ink, palette.surface),
                6.0,
                msg=f"{palette.name} 卡片文字对比度不足",
            )

    def test_legacy_theme_names_migrate(self):
        self.assertEqual(normalize_theme("深色"), "night")
        self.assertEqual(normalize_theme("护眼绿"), "eye")
        self.assertEqual(normalize_theme("米色"), "book")
        self.assertEqual(normalize_theme("白色"), "book")
        self.assertEqual(normalize_theme("插图背景"), "book")
        self.assertEqual(normalize_theme(None), "book")

    def test_apply_theme_updates_qss_and_palette(self):
        for key in ("night", "eye", "book"):
            apply_theme(APP, key)
            palette = get_palette(key)
            self.assertEqual(current_theme(), key)
            self.assertIn(palette.canvas, APP.styleSheet())
            self.assertIn(palette.accent, APP.styleSheet())
            self.assertEqual(
                APP.palette().window().color().name().lower(),
                palette.canvas.lower(),
            )

    def test_assets_are_generated(self):
        from jlwriter.ui.literary.assets import ensure_assets

        for key in ("night", "eye", "book"):
            palette = get_palette(key)
            assets = ensure_assets(palette)
            for name in ("check", "radio", "chevron", "chevron_up", "search", "texture"):
                self.assertTrue(Path(assets[name]).exists(), msg=f"{key}/{name}")


class WidgetTests(unittest.TestCase):
    def setUp(self) -> None:
        apply_theme(APP, "book")

    def test_framed_dialog_structure_and_buttons(self):
        dialog = FramedDialog(title="新建书籍", subtitle="题签")
        field = Field("书名", required=True)
        dialog.add_body(field)
        button = dialog.add_button("保存", dialog.accept, variant="primary", default=True)
        self.assertIsInstance(button, LiteraryButton)
        self.assertEqual(button.property("variant"), "primary")
        self.assertTrue(button.isDefault())
        self.assertIsNotNone(dialog.header)
        self.assertEqual(dialog.header.title_label.text(), "新建书籍")

    def test_field_error_state(self):
        field = Field("书名", required=True)
        field.set_error("书名不能为空")
        self.assertEqual(field.helper.property("role"), "error")
        self.assertFalse(field.helper.isHidden())
        self.assertEqual(field.editor.property("invalid"), True)
        field.clear_error()
        self.assertTrue(field.helper.isHidden())

    def test_toggle_switch_is_checkable(self):
        switch = ToggleSwitch()
        self.assertFalse(switch.isChecked())
        switch.setChecked(True)
        self.assertTrue(switch.isChecked())

    def test_theme_switcher_emits_selected_key(self):
        switcher = ThemeSwitcher("book")
        received = []
        switcher.theme_changed.connect(received.append)
        switcher._buttons["night"].click()
        self.assertEqual(received, ["night"])
        self.assertTrue(switcher._buttons["night"].isChecked())
        self.assertFalse(switcher._buttons["book"].isChecked())

    def test_skin_adds_header_to_plain_dialog(self):
        dialog = QDialog()
        dialog.setWindowTitle("章节选择")
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("第一章 来信"))
        layout.addWidget(QPushButton("打开"))

        polish_dialog(dialog)
        headers = dialog.findChildren(DialogHeader)
        self.assertEqual(len(headers), 1)
        self.assertTrue(dialog.property("_literaryHeader"))

    def test_screenshot_renders(self):
        apply_theme(APP, "night")
        dialog = FramedDialog(title="夜读", subtitle="青灯黄卷")
        dialog.add_body(Field("题名"))
        dialog.add_button("关闭", dialog.accept)
        dialog.resize(420, 260)
        dialog.show()
        APP.processEvents()
        pixmap = dialog.grab()
        self.assertFalse(pixmap.isNull())
        out = Path(__file__).resolve().parent / "_artifacts" / "night-dialog.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        self.assertTrue(pixmap.save(str(out)))
        dialog.close()

    def test_fit_dialog_to_screen(self):
        from jlwriter.ui.literary.skin import fit_dialog_to_screen

        dialog = FramedDialog(title="超大对话框")
        dialog.resize(4000, 3000)
        dialog.show()
        APP.processEvents()
        fit_dialog_to_screen(dialog)
        available = APP.primaryScreen().availableGeometry()
        self.assertLessEqual(dialog.width(), int(available.width() * 0.94) + 2)
        self.assertLessEqual(dialog.height(), int(available.height() * 0.90) + 2)
        frame = dialog.frameGeometry()
        self.assertGreaterEqual(frame.x(), available.x() - 2)
        self.assertGreaterEqual(frame.y(), available.y() - 2)
        self.assertLessEqual(frame.right(), available.right() + 2)
        self.assertLessEqual(frame.bottom(), available.bottom() + 2)
        dialog.close()

    def test_qss_scale_reduces_pixels(self):
        from jlwriter.ui.literary.assets import ensure_assets
        from jlwriter.ui.literary.stylesheet import build_qss

        palette = get_palette("book")
        assets = ensure_assets(palette)
        full = build_qss(palette, assets, 1.0)
        compact = build_qss(palette, assets, 0.8)
        self.assertIn("font-size: 13px", full)
        self.assertIn("font-size: 10px", compact)

    def test_default_scale_is_compact(self):
        from jlwriter.ui.literary import current_scale

        self.assertLessEqual(current_scale(), 1.0)
        self.assertGreaterEqual(current_scale(), 0.8)

    def test_close_button_is_painted_and_square(self):
        from jlwriter.ui.literary import LiteraryCloseButton

        button = LiteraryCloseButton("关闭")
        button.show()
        APP.processEvents()
        self.assertEqual(button.width(), 28)
        self.assertEqual(button.height(), 28)
        self.assertFalse(button.grab().isNull())
        button.close()

    def test_archive_list_and_editor_scroll_independently(self):
        from jlwriter.character_dialog import CharacterDialog
        from jlwriter.models import CharacterProfile, StoryProject

        project = StoryProject(title="档案测试")
        for index in range(24):
            project.characters.append(CharacterProfile(name=f"角色{index:02d}"))

        dialog = CharacterDialog(project)
        dialog.show()
        APP.processEvents()
        # 模拟小屏：列表必须自己滚动，而不是把窗口撑高
        dialog.resize(1200, 680)
        APP.processEvents()
        self.assertIsNone(dialog._body_scroll)
        self.assertGreater(
            dialog.character_tab.list_widget.verticalScrollBar().maximum(), 0
        )
        self.assertIsNotNone(dialog.character_tab.right_scroll)
        available = APP.primaryScreen().availableGeometry()
        self.assertLessEqual(dialog.height(), int(available.height() * 0.90) + 2)
        dialog.close()

    def test_large_dialog_shrinks_to_screen(self):
        from jlwriter.ai_settings_dialog import AISettingsDialog

        dialog = AISettingsDialog()
        dialog.show()
        APP.processEvents()
        available = APP.primaryScreen().availableGeometry()
        self.assertLessEqual(dialog.width(), int(available.width() * 0.94) + 2)
        self.assertLessEqual(dialog.height(), int(available.height() * 0.90) + 2)
        self.assertTrue(dialog._body_scroll.isVisible())
        dialog.close()


class DialogCoverageTests(unittest.TestCase):
    """确认主程序里的对话框都接入了新基类。"""

    DIALOGS = [
        ("book_meta_dialog", "BookMetaDialog"),
        ("chapter_select_dialog", "ChapterSelectDialog"),
        ("export_dialog", "ExportDialog"),
        ("extraction_preview_dialog", "ExtractionPreviewDialog"),
        ("first_chapter_dialog", "FirstChapterDialog"),
        ("knowledge_select_dialog", "KnowledgeSelectDialog"),
        ("project_info_dialog", "ProjectInfoDialog"),
        ("relation_editor", "RelationEditDialog"),
        ("search_dialog", "BookSearchDialog"),
        ("world_state_dialog", "WorldStateDialog"),
        ("ai_settings_dialog", "AISettingsDialog"),
        ("bookshelf_dialog", "BookshelfDialog"),
        ("planner_dialog", "PlannerDialog"),
        ("chapter_planner_dialog", "ChapterPlannerDialog"),
        ("character_dialog", "CharacterDialog"),
        ("planner_init_choice_dialog", "PlannerInitChoiceDialog"),
        ("planner_regenerate_dialog", "RegenerateStageDialog"),
        ("plan_deviation_dialog", "PlanDeviationDialog"),
        ("plan_deviation_dialog", "CorrectionPreviewDialog"),
        ("preset_browser_dialog", "PresetBrowserDialog"),
        ("preset_browser_dialog", "SavePresetDialog"),
        ("prompt_history_viewer", "PromptViewerDialog"),
        ("review_report_dialog", "ReviewReportDialog"),
        ("main_window", "AgreementDialog"),
    ]

    def test_all_dialogs_use_literary_base(self):
        for module_name, class_name in self.DIALOGS:
            module = importlib.import_module(f"jlwriter.{module_name}")
            cls = getattr(module, class_name)
            self.assertTrue(
                issubclass(cls, LiteraryDialog),
                msg=f"{module_name}.{class_name} 没有接入文学风基类",
            )


if __name__ == "__main__":
    unittest.main()
