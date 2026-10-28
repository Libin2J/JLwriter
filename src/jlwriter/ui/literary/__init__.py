"""JLwriter 文学风 UI 设计系统（可移植）。

快速开始::

    from PyQt5.QtWidgets import QApplication
    from jlwriter.ui.literary import apply_theme, FramedDialog, Field, LiteraryButton

    app = QApplication([])
    apply_theme(app, "book")          # night / eye / book

    dlg = FramedDialog(title="新建书籍", subtitle="题签 · 书名与封面")
    field = Field("书名", hint="必填", required=True)
    dlg.add_body(field)
    dlg.add_button("取消", dlg.reject)
    dlg.add_button("保存", dlg.accept, variant="primary", default=True)
"""
from __future__ import annotations

from .controller import (
    LiteraryTheme,
    apply_theme,
    controller,
    current_palette,
    current_scale,
    current_theme,
    install,
)
from .themes import (
    BOOK,
    DEFAULT_THEME,
    EYE,
    METRICS,
    NIGHT,
    PALETTES,
    THEME_ORDER,
    Palette,
    app_font,
    get_palette,
    kai_family,
    normalize_theme,
    serif_family,
    theme_choices,
)
from .widgets import (
    Card,
    DialogHeader,
    EmptyState,
    Field,
    FramedDialog,
    LiteraryButton,
    LiteraryCloseButton,
    LiteraryComboBox,
    LiteraryDialog,
    Ornament,
    SearchField,
    Seal,
    Tag,
    ThemeSwitcher,
    ToggleSwitch,
    repolish,
)

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # 主题
    "NIGHT",
    "EYE",
    "BOOK",
    "PALETTES",
    "THEME_ORDER",
    "DEFAULT_THEME",
    "Palette",
    "METRICS",
    "apply_theme",
    "install",
    "controller",
    "current_palette",
    "current_scale",
    "current_theme",
    "get_palette",
    "normalize_theme",
    "theme_choices",
    "app_font",
    "serif_family",
    "kai_family",
    "LiteraryTheme",
    # 控件
    "LiteraryDialog",
    "FramedDialog",
    "DialogHeader",
    "Ornament",
    "Seal",
    "LiteraryButton",
    "LiteraryCloseButton",
    "Field",
    "SearchField",
    "LiteraryComboBox",
    "ToggleSwitch",
    "ThemeSwitcher",
    "Card",
    "Tag",
    "EmptyState",
    "repolish",
]
