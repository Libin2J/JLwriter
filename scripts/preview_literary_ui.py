"""生成文学风 UI 的预览图。

用法（在仓库根目录）::

    python scripts/preview_literary_ui.py
    python scripts/preview_literary_ui.py --out docs/ui-preview --themes night,eye,book

输出：每套主题下若干真实对话框的截图，外加一个 ``index.html`` 画廊。
不访问网络、不读写用户项目，数据目录指向 ``tests/_tmp/preview_data``。
"""
from __future__ import annotations

import argparse
import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("JLWRITER_DATA_DIR", str(ROOT / "tests" / "_tmp" / "preview_data"))

from PyQt5.QtWidgets import (  # noqa: E402
    QApplication,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt  # noqa: E402

from jlwriter.ui.literary import (  # noqa: E402
    Field,
    FramedDialog,
    LiteraryButton,
    LiteraryComboBox,
    Tag,
    ThemeSwitcher,
    ToggleSwitch,
    apply_theme,
    install,
    theme_choices,
)


class ShowcaseDialog(FramedDialog):
    """把设计系统的控件摆在一起，作为样式基准页。"""

    def __init__(self):
        super().__init__(
            title="控件样张",
            subtitle="一页看清题头、字段、按钮与主题切换",
            seal_text="墨",
            motto="字如其人，器如其文",
        )
        self.resize(760, 540)

        columns = QHBoxLayout()
        columns.setSpacing(30)

        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(Field("书名", hint="必填", required=True))
        left.addWidget(Field("作者", hint="可选"))
        combo = LiteraryComboBox()
        combo.addItems(["简洁流畅", "华丽优美", "悬疑紧张"])
        left.addWidget(Field("叙事风格", editor=combo))

        switch_row = QHBoxLayout()
        switch_label = QLabel("护眼提示")
        switch_label.setProperty("role", "field-label")
        switch_row.addWidget(switch_label)
        switch_row.addStretch(1)
        switch_row.addWidget(ToggleSwitch())
        left.addLayout(switch_row)
        left.addStretch(1)

        right = QVBoxLayout()
        right.setSpacing(10)
        tags = QHBoxLayout()
        for text in ("长篇", "群像", "悬疑"):
            tags.addWidget(Tag(text))
        tags.addStretch(1)
        right.addLayout(tags)
        for text, variant in (
            ("主要操作", "primary"),
            ("次要操作", "quiet"),
            ("文字操作", "ghost"),
            ("危险操作", "danger"),
        ):
            button = LiteraryButton(text, variant=variant)
            button.setMaximumWidth(200)
            right.addWidget(button, 0, Qt.AlignLeft)
        right.addStretch(1)
        theme_label = QLabel("主题切换")
        theme_label.setProperty("role", "field-label")
        right.addWidget(theme_label)
        right.addWidget(ThemeSwitcher())
        right.addStretch(1)

        columns.addLayout(left, 1)
        columns.addLayout(right, 1)
        body = QWidget()
        body.setLayout(columns)
        self.add_body(body, 1)
        self.add_button("取消", self.reject, variant="ghost")
        self.add_button("保存", self.accept, variant="primary", default=True)


def _sample_project():
    from jlwriter.models import Chapter, CharacterProfile, StoryProject, Volume

    project = StoryProject(title="长夜将明")
    volume = Volume("第一卷 雨夜")
    chapter = Chapter(
        "第一章 来信",
        content=(
            "雨落在青石板上，檐角的水一滴一滴敲着夜色。"
            "少年在门缝里发现一封来自未来的信，信封上只有他的名字。"
        ),
    )
    volume.chapters.append(chapter)
    project.volumes.append(volume)
    for index in range(40):
        project.characters.append(CharacterProfile(name=f"角色{index:02d}"))
    return project


def build_dialogs():
    from jlwriter.book_meta_dialog import BookMetaDialog
    from jlwriter.character_dialog import CharacterDialog
    from jlwriter.export_dialog import ExportDialog
    from jlwriter.main_window import AgreementDialog
    from jlwriter.planner_init_choice_dialog import PlannerInitChoiceDialog
    from jlwriter.search_dialog import BookSearchDialog

    project = _sample_project()
    summary = {
        "premise": "少年在雨夜捡到一封来自未来的信",
        "background": "近未来的江南小城",
        "outline": "三幕式成长故事",
    }

    def book_meta():
        dialog = BookMetaDialog()
        dialog.title_edit.setText("长夜将明")
        dialog.author_edit.setText("沈砚")
        dialog.desc_edit.setPlainText(
            "一封来自未来的信，把江南小城的雨夜拉长成十年。"
        )
        return dialog, (700, 600)

    return [
        ("book-meta", "新建书籍", *book_meta()),
        (
            "planner",
            "策划入口",
            PlannerInitChoiceDialog(summary),
            None,
        ),
        (
            "search",
            "全文搜索",
            BookSearchDialog(project, "雨"),
            None,
        ),
        (
            "export",
            "导出设置",
            ExportDialog(project),
            None,
        ),
        (
            "agreement",
            "用户协议",
            AgreementDialog(),
            None,
        ),
        ("showcase", "控件样张", ShowcaseDialog(), None),
        ("archive", "故事档案", CharacterDialog(project), None),
    ]


def _render(theme: str, out_dir: Path):
    from PyQt5.QtWidgets import QApplication

    app = QApplication.instance()
    apply_theme(app, theme)
    shots = []
    for slug, label, dialog, size in build_dialogs():
        if size:
            dialog.resize(*size)
        dialog.show()
        app.processEvents()
        path = out_dir / f"{theme}-{slug}.png"
        dialog.grab().save(str(path))
        dialog.close()
        shots.append((slug, label, path.name))
        print(f"  {theme}/{slug}: {path}")
    return shots


def _write_gallery(out_dir: Path, gallery: dict):
    names = dict((key, name) for key, name, _ in theme_choices())
    blocks = []
    for theme, shots in gallery.items():
        cards = "\n".join(
            f'<figure><img src="{html.escape(filename)}" alt="{html.escape(label)}">'
            f"<figcaption>{html.escape(label)}</figcaption></figure>"
            for _, label, filename in shots
        )
        blocks.append(
            f'<section><h2>{html.escape(names[theme])} · {theme}</h2>'
            f'<div class="grid">{cards}</div></section>'
        )
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>JLwriter 文学风界面预览</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ margin: 0; padding: 40px; background: #efe6d6; color: #33291f;
         font-family: "Noto Serif SC", "Songti SC", "SimSun", serif; }}
  h1 {{ font-size: 28px; font-weight: 600; margin: 0 0 6px; }}
  p.lead {{ color: #8a7860; margin: 0 0 34px; }}
  h2 {{ font-size: 18px; margin: 38px 0 14px; color: #9e3b2c; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
           gap: 20px; }}
  figure {{ margin: 0; background: #f8f1e2; border: 1px solid #d8c5a9;
            border-radius: 3px; overflow: hidden; }}
  img {{ display: block; width: 100%; height: auto; }}
  figcaption {{ padding: 9px 12px; font-size: 12px; color: #8a7860;
                border-top: 1px solid #d8c5a9; }}
</style></head>
<body>
<h1>JLwriter 文学风界面</h1>
<p class="lead">夜读 / 护眼 / 书卷 · 对话框重设计预览（真实控件渲染，非效果图）</p>
{''.join(blocks)}
</body></html>
"""
    (out_dir / "index.html").write_text(document, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="生成文学风 UI 预览图")
    parser.add_argument("--out", default=str(ROOT / "docs" / "ui-preview"))
    parser.add_argument("--themes", default="night,eye,book")
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    themes = [theme.strip() for theme in args.themes.split(",") if theme.strip()]

    app = QApplication.instance() or QApplication([])
    install(app, themes[0])

    gallery = {}
    for theme in themes:
        print(f"[{theme}]")
        gallery[theme] = _render(theme, out_dir)

    _write_gallery(out_dir, gallery)
    print(f"预览已生成：{out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
