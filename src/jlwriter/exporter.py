"""
导出模块：支持 TXT / Markdown / PDF / 长图(PNG)
"""
from html import escape as html_escape

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QTextDocument, QPainter, QImage, QColor, QFont
from PyQt5.QtPrintSupport import QPrinter


MAX_IMAGE_HEIGHT = 30000      # Qt QImage 高度上限保护
DEFAULT_IMAGE_WIDTH = 900


# ============================================================
# 内容组装
# ============================================================

def build_chapter_volumes(project, chapters=None):
    """
    将 project 中的章节按卷分组。
    chapters: [(vol_idx, ch_idx), ...]，None 表示全部
    返回：[{title, chapters: [{title, content, summary}]}]
    """
    if chapters is None:
        target_set = None
    else:
        target_set = set(chapters)

    volumes = []
    for vi, vol in enumerate(project.volumes):
        ch_items = []
        for ci, ch in enumerate(vol.chapters):
            if target_set is not None and (vi, ci) not in target_set:
                continue
            ch_items.append({
                "title": ch.title or f"第{ci + 1}章",
                "content": ch.content or "",
                "summary": ch.summary or "",
            })
        if ch_items:
            volumes.append({
                "title": vol.title or f"第{vi + 1}卷",
                "summary": vol.summary or "",
                "chapters": ch_items,
            })
    return volumes


def build_story_info(project):
    """组装故事设定数据"""
    return {
        "title": project.title or "未命名故事",
        "premise": project.premise or "",
        "story_background": project.story_background or "",
        "power_system": project.power_system or "",
        "outline": project.outline or "",
        "settings_book": project.settings_book or "",
        "characters": project.characters,
        "monsters": project.monsters,  # 新增
        "locations": project.locations,
        "organizations": project.organizations,
        "items": project.items,
        "relations": project.relations,
        "world_states": project.world_states,
    }


# ============================================================
# TXT 导出
# ============================================================

def export_txt(volumes, output_path, book_title=""):
    lines = []
    if book_title:
        lines.append(book_title)
        lines.append("=" * (len(book_title) * 2))
        lines.append("")
    for vol in volumes:
        lines.append("")
        lines.append(f"【{vol['title']}】")
        lines.append("")
        for ch in vol["chapters"]:
            lines.append(ch["title"])
            lines.append("-" * 30)
            lines.append("")
            lines.append(ch["content"].rstrip())
            lines.append("")
            lines.append("")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# Markdown 导出
# ============================================================

def export_markdown(volumes, output_path, book_title=""):
    lines = []
    if book_title:
        lines.append(f"# {book_title}")
        lines.append("")
    for vol in volumes:
        lines.append(f"## {vol['title']}")
        lines.append("")
        for ch in vol["chapters"]:
            lines.append(f"### {ch['title']}")
            lines.append("")
            content = ch["content"].rstrip()
            if content:
                for para in content.split("\n"):
                    if para.strip():
                        lines.append(para)
                    else:
                        lines.append("")
            lines.append("")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# 故事设定导出
# ============================================================

def export_story_info_markdown(project, output_path):
    info = build_story_info(project)
    md = []
    md.append(f"# {info['title']} - 故事设定")
    md.append("")

    if info["premise"]:
        md.append("## 核心矛盾")
        md.append(info["premise"])
        md.append("")

    if info["story_background"]:
        md.append("## 故事背景")
        md.append(info["story_background"])
        md.append("")

    if info["power_system"]:
        md.append("## 力量体系")
        md.append(info["power_system"])
        md.append("")

    if info["outline"]:
        md.append("## 故事总纲")
        md.append(info["outline"])
        md.append("")

    if info["characters"]:
        md.append("## 角色档案")
        for c in info["characters"]:
            md.append(f"### {c.name}")
            if c.aliases:
                md.append(f"- 别名：{'、'.join(c.aliases)}")
            if c.appearance:
                md.append(f"- 外貌：{c.appearance}")
            if c.personality:
                md.append(f"- 性格：{c.personality}")
            if c.habits:
                md.append(f"- 习惯：{c.habits}")
            if c.timeline:
                md.append("- 时间线：")
                for ev in c.timeline:
                    md.append(f"  - {ev}")
            md.append("")

    if info.get("monsters"):
        md.append("## 怪物档案")
        for m in info["monsters"]:
            md.append(f"### {m.name}")
            if m.aliases:
                md.append(f"- 别名：{'、'.join(m.aliases)}")
            if m.category:
                md.append(f"- 纲目：{m.category}")
            if m.appearance:
                md.append(f"- 外形：{m.appearance}")
            if m.behavior_ability:
                md.append(f"- 行为与能力：{m.behavior_ability}")
            md.append("")

    if info["organizations"]:
        md.append("## 主要势力")
        for o in info["organizations"]:
            md.append(f"### {o.name}（{o.nature}）")
            if o.description:
                md.append(o.description)
            if o.members:
                md.append(f"- 成员：{'、'.join(o.members)}")
            md.append("")

    if info["locations"]:
        md.append("## 主要地点")
        for l in info["locations"]:
            parent = f"（上级：{l.parent}）" if l.parent else ""
            md.append(f"- **{l.name}**{parent}（{l.level}）：{l.description}")
        md.append("")

    if info["items"]:
        md.append("## 重要物品")
        for i in info["items"]:
            owner = f"｜归属：{i.owner}" if i.owner else ""
            md.append(
                f"- **{i.name}**（{i.type}）：{i.description}"
                f"｜能力：{i.ability}{owner}"
            )
        md.append("")

    if info["relations"]:
        md.append("## 关系网络")
        for r in info["relations"]:
            a = r.get("from", "")
            b = r.get("to", "")
            typ = r.get("type", "")
            desc = r.get("description", "")
            line = f"- {a} → {b}（{typ}）"
            if desc:
                line += f" {desc}"
            md.append(line)
        md.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(md))


# ============================================================
# HTML 构建（PDF / 长图共用）
# ============================================================

def _chapters_to_html(volumes, book_title="", font_family="Microsoft YaHei",
                      font_size=13, for_pdf=False):
    """将章节内容转为 HTML"""
    parts = []
    parts.append('<html><head><meta charset="utf-8"></head><body>')
    parts.append(
        f'<div style="font-family: \'{font_family}\'; '
        f'font-size: {font_size}pt; line-height: 1.8; color: #222;">'
    )

    if book_title:
        parts.append(
            f'<h1 style="text-align:center; font-size: '
            f'{int(font_size * 2)}pt; margin-bottom: 40px;">'
            f'{html_escape(book_title)}</h1>'
        )

    first_vol = True
    for vol in volumes:
        if not first_vol and for_pdf:
            parts.append('<div style="page-break-before: always;"></div>')
        first_vol = False

        parts.append(
            f'<h2 style="font-size: {int(font_size * 1.6)}pt; '
            f'margin-top: 40px; margin-bottom: 20px;">'
            f'{html_escape(vol["title"])}</h2>'
        )

        for ch in vol["chapters"]:
            parts.append(
                f'<h3 style="font-size: {int(font_size * 1.3)}pt; '
                f'margin-top: 30px; margin-bottom: 16px;">'
                f'{html_escape(ch["title"])}</h3>'
            )
            content = ch["content"] or ""
            for para in content.split("\n"):
                if para.strip():
                    parts.append(
                        f'<p style="text-indent: 2em; margin: 8px 0;">'
                        f'{html_escape(para)}</p>'
                    )
                else:
                    parts.append('<p style="margin: 8px 0;">&nbsp;</p>')

    parts.append('</div></body></html>')
    return "".join(parts)


def _story_info_to_html(project, font_family="Microsoft YaHei", font_size=13):
    """故事设定转 HTML"""
    info = build_story_info(project)
    parts = []
    parts.append('<html><head><meta charset="utf-8"></head><body>')
    parts.append(
        f'<div style="font-family: \'{font_family}\'; '
        f'font-size: {font_size}pt; line-height: 1.7; color: #222;">'
    )
    parts.append(f'<h1 style="text-align:center;">{html_escape(info["title"])} · 故事设定</h1>')

    def section(title, text):
        if not text:
            return
        parts.append(f'<h2 style="margin-top:24px;">{html_escape(title)}</h2>')
        for para in text.split("\n"):
            if para.strip():
                parts.append(f'<p style="margin: 6px 0;">{html_escape(para)}</p>')

    section("核心矛盾", info["premise"])
    section("故事背景", info["story_background"])
    section("力量体系", info["power_system"])
    section("故事总纲", info["outline"])

    if info["characters"]:
        parts.append('<h2>角色档案</h2>')
        for c in info["characters"]:
            parts.append(f'<h3 style="margin-top:14px;">{html_escape(c.name)}</h3>')
            lines = []
            if c.aliases:
                lines.append(f"别名：{'、'.join(c.aliases)}")
            if c.appearance:
                lines.append(f"外貌：{c.appearance}")
            if c.personality:
                lines.append(f"性格：{c.personality}")
            if c.habits:
                lines.append(f"习惯：{c.habits}")
            for l in lines:
                parts.append(f'<p style="margin:2px 0;">{html_escape(l)}</p>')
            if c.timeline:
                parts.append('<p style="margin:2px 0;">时间线：</p>')
                for ev in c.timeline:
                    parts.append(f'<p style="margin:2px 0 2px 20px;">· {html_escape(ev)}</p>')

    if info.get("monsters"):
        parts.append('<h2>怪物档案</h2>')
        for m in info["monsters"]:
            parts.append(f'<h3 style="margin-top:14px;">{html_escape(m.name)}</h3>')
            if m.aliases:
                parts.append(
                    f'<p>别名：{html_escape("、".join(m.aliases))}</p>'
                )
            if m.category:
                parts.append(f'<p>纲目：{html_escape(m.category)}</p>')
            if m.appearance:
                parts.append(f'<p>外形：{html_escape(m.appearance)}</p>')
            if m.behavior_ability:
                parts.append(
                    f'<p>行为与能力：{html_escape(m.behavior_ability)}</p>'
                )

    if info["organizations"]:
        parts.append('<h2>主要势力</h2>')
        for o in info["organizations"]:
            parts.append(
                f'<h3 style="margin-top:14px;">'
                f'{html_escape(o.name)}（{html_escape(o.nature)}）</h3>'
            )
            if o.description:
                parts.append(f'<p>{html_escape(o.description)}</p>')
            if o.members:
                parts.append(f'<p>成员：{html_escape("、".join(o.members))}</p>')

    if info["locations"]:
        parts.append('<h2>主要地点</h2>')
        for l in info["locations"]:
            parent = f"（上级：{l.parent}）" if l.parent else ""
            parts.append(
                f'<p><b>{html_escape(l.name)}</b>{html_escape(parent)}'
                f'（{html_escape(l.level)}）：{html_escape(l.description)}</p>'
            )

    if info["items"]:
        parts.append('<h2>重要物品</h2>')
        for i in info["items"]:
            owner = f"｜归属：{i.owner}" if i.owner else ""
            parts.append(
                f'<p><b>{html_escape(i.name)}</b>（{html_escape(i.type)}）：'
                f'{html_escape(i.description)}｜能力：{html_escape(i.ability)}'
                f'{html_escape(owner)}</p>'
            )

    if info["relations"]:
        parts.append('<h2>关系网络</h2>')
        for r in info["relations"]:
            a = r.get("from", "")
            b = r.get("to", "")
            typ = r.get("type", "")
            desc = r.get("description", "")
            line = f"{a} → {b}（{typ}）"
            if desc:
                line += f" {desc}"
            parts.append(f'<p style="margin:2px 0;">· {html_escape(line)}</p>')

    parts.append('</div></body></html>')
    return "".join(parts)


# ============================================================
# PDF 导出
# ============================================================

def export_pdf(html_content, output_path, font_family="Microsoft YaHei"):
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(output_path)
    printer.setPageSize(QPrinter.A4)
    printer.setPageMargins(20, 20, 20, 20, QPrinter.Millimeter)

    doc = QTextDocument()
    doc.setDefaultFont(QFont(font_family, 12))
    doc.setHtml(html_content)
    doc.print_(printer)


# ============================================================
# 长图导出
# ============================================================

def export_long_image(html_content, output_path,
                      width=DEFAULT_IMAGE_WIDTH,
                      font_family="Microsoft YaHei",
                      font_size=14,
                      bg_color="#F8F5EF"):
    """
    渲染为长图。
    - 内容宽度固定为 width
    - 高度自适应，超过 MAX_IMAGE_HEIGHT 时截断
    """
    doc = QTextDocument()
    font = QFont(font_family, font_size)
    doc.setDefaultFont(font)
    doc.setHtml(html_content)

    # 让文档按指定宽度排版
    padding = 40
    text_width = width - padding * 2
    doc.setTextWidth(text_width)

    height = int(doc.size().height()) + padding * 2
    if height > MAX_IMAGE_HEIGHT:
        height = MAX_IMAGE_HEIGHT

    image = QImage(width, height, QImage.Format_ARGB32)
    image.fill(QColor(bg_color))

    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.TextAntialiasing)
    painter.translate(padding, padding)
    # 用剩余高度绘制内容
    doc.drawContents(painter, QRectF(0, 0, text_width, height - padding * 2))
    painter.end()

    image.save(output_path, "PNG")


# ============================================================
# 高层接口
# ============================================================

def export_chapters(project, chapters, fmt, output_path,
                    font_family="Microsoft YaHei", font_size=13):
    """
    统一入口。
    chapters: [(vol_idx, ch_idx), ...] 或 None（全书）
    fmt: "txt" / "md" / "pdf" / "png"
    """
    volumes = build_chapter_volumes(project, chapters)
    if not volumes:
        raise ValueError("没有可导出的章节")

    book_title = project.title or ""
    if fmt == "txt":
        export_txt(volumes, output_path, book_title)
    elif fmt == "md":
        export_markdown(volumes, output_path, book_title)
    elif fmt == "pdf":
        html = _chapters_to_html(
            volumes, book_title,
            font_family=font_family, font_size=font_size,
            for_pdf=True,
        )
        export_pdf(html, output_path, font_family=font_family)
    elif fmt == "png":
        html = _chapters_to_html(
            volumes, book_title,
            font_family=font_family, font_size=font_size + 1,
            for_pdf=False,
        )
        export_long_image(
            html, output_path,
            font_family=font_family, font_size=font_size + 1,
        )
    else:
        raise ValueError(f"不支持的格式：{fmt}")


def export_story_info(project, fmt, output_path, font_family="Microsoft YaHei"):
    """导出故事设定"""
    if fmt == "md":
        export_story_info_markdown(project, output_path)
    elif fmt == "txt":
        md_path = output_path
        export_story_info_markdown(project, md_path)
    elif fmt == "pdf":
        html = _story_info_to_html(project, font_family=font_family)
        export_pdf(html, output_path, font_family=font_family)
    elif fmt == "png":
        html = _story_info_to_html(project, font_family=font_family)
        export_long_image(html, output_path, font_family=font_family)
    else:
        raise ValueError(f"不支持的格式：{fmt}")