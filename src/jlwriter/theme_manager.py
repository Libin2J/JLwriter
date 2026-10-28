"""写作软件整体主题风格定义（兼容层）。

真正的视觉系统在 :mod:`jlwriter.ui.literary`。这里只保留旧调用点需要的
``ThemeManager.apply_theme`` / ``theme_key``，并把旧主题名自动迁移：

* 深色        → 夜读 ``night``
* 护眼绿      → 护眼 ``eye``
* 白色 / 米色 → 书卷 ``book``
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtWidgets import QApplication

from .ui.literary import apply_theme as _apply_theme
from .ui.literary import normalize_theme


class ThemeManager:
    """主题门面：保持旧 API，内部委托给文学风设计系统。"""

    @classmethod
    def theme_key(cls, theme_name: Optional[str]) -> str:
        return normalize_theme(theme_name)

    @classmethod
    def apply_theme(
        cls, app: QApplication, theme_name: str, main_window=None, scale=None
    ):
        key = _apply_theme(app or QApplication.instance(), theme_name, scale)
        if main_window is not None:
            main_window.setProperty("theme", key)
            # 主题切换后，编辑器字体可能被全局样式重置，交给主窗口自行恢复
            refresh = getattr(main_window, "_restore_editor_font", None)
            if callable(refresh):
                refresh()
        return key
