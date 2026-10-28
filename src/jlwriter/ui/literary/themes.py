"""文学风主题的令牌定义：三套配色、字体与度量。

设计目标
--------
* **夜读**：墨蓝夜色 + 暖金，适合深夜长时间写作；
* **护眼**：青瓷纸色 + 苔绿，降低蓝光与对比刺激；
* **书卷**：旧纸米色 + 朱砂，最接近纸质书的阅读体验。

所有控件只读取这里的令牌，不直接写死颜色，因此新增主题只需再加一份
:class:`Palette`，无需改控件代码。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Optional, Tuple

from PyQt5.QtCore import QSettings
from PyQt5.QtGui import QColor, QFont, QFontDatabase, QPalette


@dataclass(frozen=True)
class Palette:
    """一套完整的主题配色。"""

    key: str
    name: str
    description: str

    # 表面层次：画布 → 卡片 → 浮起 → 凹陷
    canvas: str
    surface: str
    surface_alt: str
    sunken: str

    # 墨色层次：正文 → 次级 → 弱化 → 极弱
    ink: str
    ink_soft: str
    ink_muted: str
    ink_faint: str

    # 强调色（印章色）
    accent: str
    accent_soft: str
    accent_strong: str
    on_accent: str

    line: str
    line_strong: str

    danger: str
    success: str
    warning: str

    selection: str
    selection_text: str

    texture: str = "paper"
    texture_alpha: int = 10


NIGHT = Palette(
    key="night",
    name="夜读",
    description="墨蓝夜色与暖金灯火，适合夜间长时间写作。",
    canvas="#14161C",
    surface="#1B1E26",
    surface_alt="#232733",
    sunken="#101218",
    ink="#E8E1D2",
    ink_soft="#C9C1AF",
    ink_muted="#948C7B",
    ink_faint="#665F53",
    accent="#C8A464",
    accent_soft="#332B1D",
    accent_strong="#E0BC7A",
    on_accent="#171410",
    line="#2C313C",
    line_strong="#454B5A",
    danger="#D97A6C",
    success="#8FBF9F",
    warning="#D8B36A",
    selection="#4A3D26",
    selection_text="#F3EAD8",
    texture="grain",
    texture_alpha=8,
)

EYE = Palette(
    key="eye",
    name="护眼",
    description="青瓷纸色与苔绿，柔和低对比，缓解长时间注视的疲劳。",
    canvas="#DCE7D6",
    surface="#E9F0E3",
    surface_alt="#F2F7ED",
    sunken="#CFDCC8",
    ink="#2B382D",
    ink_soft="#455647",
    ink_muted="#6D7F6F",
    ink_faint="#97A697",
    accent="#557A5C",
    accent_soft="#C6D8C0",
    accent_strong="#3D5C44",
    on_accent="#F4F8F0",
    line="#C2D2B9",
    line_strong="#A5B99D",
    danger="#A65B4E",
    success="#4F7A55",
    warning="#9A7B3F",
    selection="#BFD5B8",
    selection_text="#223026",
    texture="fiber",
    texture_alpha=9,
)

BOOK = Palette(
    key="book",
    name="书卷",
    description="旧纸米色与朱砂印章，最接近纸质书的阅读与书写体验。",
    canvas="#F1E7D6",
    surface="#F8F1E2",
    surface_alt="#FCF7EC",
    sunken="#E7DBC6",
    ink="#332A22",
    ink_soft="#584A3C",
    ink_muted="#8A7860",
    ink_faint="#B3A288",
    accent="#9E3B2C",
    accent_soft="#EAD3C8",
    accent_strong="#7C2A1F",
    on_accent="#FBF4E8",
    line="#D8C5A9",
    line_strong="#BFA98C",
    danger="#A33A2C",
    success="#5F7A4E",
    warning="#9A6B2F",
    selection="#E3C9A8",
    selection_text="#2C241D",
    texture="paper",
    texture_alpha=11,
)

PALETTES: Dict[str, Palette] = {p.key: p for p in (NIGHT, EYE, BOOK)}
THEME_ORDER: Tuple[str, ...] = ("night", "eye", "book")
DEFAULT_THEME = "book"
DEFAULT_UI_SCALE = 0.9
UI_SCALE_ENV = "JLWRITER_UI_SCALE"

# 旧版本（v1.1 之前）使用的主题名，升级时自动迁移
_LEGACY_NAMES = {
    "深色": "night",
    "夜间": "night",
    "night": "night",
    "护眼绿": "eye",
    "护眼": "eye",
    "eye": "eye",
    "白色": "book",
    "米色": "book",
    "书卷": "book",
    "book": "book",
    "插图背景": "book",
}


@dataclass(frozen=True)
class Metrics:
    """间距、圆角与动效。文学风偏克制：小圆角、细边框、慢动效。"""

    radius: int = 3
    page_margin_x: int = 24
    page_margin_top: int = 20
    page_margin_bottom: int = 18
    section_gap: int = 14
    field_gap: int = 5
    button_height: int = 29
    animation_ms: int = 160


METRICS = Metrics()


def _screen_ui_scale() -> float:
    """按逻辑桌面宽度给一个默认密度。

    * 2560×1600（100%）：1.0
    * 1707×1067 左右（2560×1600 @150%）：0.95
    * 1280×800（2560×1600 @200%）：0.9
    """
    try:
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        screen = app.primaryScreen() if app else None
        if screen is not None:
            width = screen.availableGeometry().width()
            if width >= 2200:
                return 1.0
            if width >= 1500:
                return 0.95
    except Exception:
        pass
    return DEFAULT_UI_SCALE


def resolve_ui_scale() -> float:
    """界面密度：优先环境变量 / 用户设置，否则按屏幕逻辑分辨率自适应。"""
    raw = os.environ.get(UI_SCALE_ENV)
    if raw is None:
        try:
            raw = QSettings("JLwriter", "JLwriter").value("ui/scale")
        except Exception:
            raw = None
    if raw in (None, ""):
        return _screen_ui_scale()
    try:
        scale = float(raw)
    except (TypeError, ValueError):
        return _screen_ui_scale()
    # 低于 80% 的旧值不再使用：它通常来自上一版的临时缩放，
    # 继续沿用会让 2560 屏上的字小到不可读。
    if scale < 0.8:
        return _screen_ui_scale()
    return max(0.8, min(1.15, scale))


def normalize_theme(value: Optional[str]) -> str:
    """把旧主题名、显示名统一成 ``night`` / ``eye`` / ``book``。"""
    if not value:
        return DEFAULT_THEME
    text = str(value).strip()
    if text in PALETTES:
        return text
    if text in _LEGACY_NAMES:
        return _LEGACY_NAMES[text]
    return DEFAULT_THEME


def get_palette(value: Optional[str]) -> Palette:
    return PALETTES[normalize_theme(value)]


def theme_choices() -> Tuple[Tuple[str, str, str], ...]:
    """``(key, 名称, 一句话说明)``，供菜单/切换器生成。"""
    return tuple((p.key, p.name, p.description) for p in (NIGHT, EYE, BOOK))


# ------------------------------------------------------------------ 字体
_SERIF_CANDIDATES = (
    "Noto Serif SC",
    "Source Han Serif SC",
    "Songti SC",
    "STSong",
    "中易宋体",
    "宋体",
    "SimSun",
    "Georgia",
    "serif",
)
_KAI_CANDIDATES = (
    "Kaiti SC",
    "STKaiti",
    "楷体",
    "KaiTi",
    "华文楷体",
    "Noto Serif SC",
    "宋体",
)
_MONO_CANDIDATES = ("JetBrains Mono", "Cascadia Mono", "Consolas", "monospace")


@lru_cache(maxsize=1)
def _families() -> Tuple[str, ...]:
    try:
        return tuple(QFontDatabase().families())
    except Exception:
        return ()


def _pick(candidates: Tuple[str, ...], fallback: str) -> str:
    families = _families()
    lowered = {name.lower(): name for name in families}
    for candidate in candidates:
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
        if candidate in families:
            return candidate
    return fallback


@lru_cache(maxsize=1)
def serif_family() -> str:
    """正文/标题的宋体族；找不到则退回系统默认。"""
    return _pick(_SERIF_CANDIDATES, "Microsoft YaHei")


@lru_cache(maxsize=1)
def kai_family() -> str:
    """引文/题跋的楷体族。"""
    return _pick(_KAI_CANDIDATES, serif_family())


@lru_cache(maxsize=1)
def mono_family() -> str:
    return _pick(_MONO_CANDIDATES, "Consolas")


def app_font(point_size: float = 10.5) -> QFont:
    """应用基础字体：宋体 + 轻微字距，避免界面过于“系统化”。"""
    family = serif_family()
    font = QFont(family)
    font.setPointSizeF(point_size)
    try:
        if hasattr(font, "setFamilies"):
            font.setFamilies([family, kai_family()])
    except Exception:  # pragma: no cover - Qt < 5.13
        pass
    font.setStyleStrategy(QFont.PreferAntialias)
    return font


# ------------------------------------------------------------------ 调色板
def qpalette(p: Palette) -> QPalette:
    """原生控件（文件对话框、工具提示等）也跟随主题。"""
    pal = QPalette()
    roles = {
        QPalette.Window: p.canvas,
        QPalette.WindowText: p.ink,
        QPalette.Base: p.surface,
        QPalette.AlternateBase: p.surface_alt,
        QPalette.Text: p.ink,
        QPalette.Button: p.surface_alt,
        QPalette.ButtonText: p.ink,
        QPalette.BrightText: p.on_accent,
        QPalette.Highlight: p.accent,
        QPalette.HighlightedText: p.on_accent,
        QPalette.ToolTipBase: p.ink,
        QPalette.ToolTipText: p.canvas,
        QPalette.Link: p.accent,
        QPalette.LinkVisited: p.accent_strong,
        QPalette.Light: p.surface_alt,
        QPalette.Midlight: p.surface,
        QPalette.Mid: p.line,
        QPalette.Dark: p.line_strong,
        QPalette.Shadow: p.sunken,
    }
    for role, value in roles.items():
        pal.setColor(role, QColor(value))
    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, QColor(p.ink_faint))
    pal.setColor(QPalette.Disabled, QPalette.Base, QColor(p.sunken))
    pal.setColor(QPalette.Disabled, QPalette.Button, QColor(p.sunken))
    try:  # Qt 5.12+
        pal.setColor(QPalette.PlaceholderText, QColor(p.ink_faint))
    except AttributeError:  # pragma: no cover
        pass
    return pal
