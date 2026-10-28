"""主题控制器：把一份 :class:`Palette` 应用成整个 QApplication 的外观。

三个入口:

* :func:`apply_theme` — 切换主题（供主窗口调用）；
* :func:`install` — 启动时安装主题与对话框修饰器；
* :func:`current_palette` — 自定义绘制的控件读取当前配色。
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import QApplication

from .assets import ensure_assets
from .stylesheet import build_qss
from .themes import (
    DEFAULT_THEME,
    Palette,
    app_font,
    get_palette,
    normalize_theme,
    qpalette,
    resolve_ui_scale,
)


class LiteraryTheme(QObject):
    """主题单例：保存当前主题，应用 QSS/调色板/字体，并广播切换信号。"""

    theme_changed = pyqtSignal(str)

    def __init__(self) -> None:
        super().__init__()
        self._key = DEFAULT_THEME
        self._scale = 1.0

    @property
    def key(self) -> str:
        return self._key

    @property
    def scale(self) -> float:
        return self._scale

    @property
    def palette(self) -> Palette:
        return get_palette(self._key)

    def apply(
        self, app: QApplication, theme: Optional[str], scale: Optional[float] = None
    ) -> str:
        key = normalize_theme(theme)
        palette = get_palette(key)
        assets = ensure_assets(palette)
        scale = resolve_ui_scale() if scale is None else max(0.8, min(1.15, float(scale)))
        app.setStyleSheet(build_qss(palette, assets, scale))
        app.setPalette(qpalette(palette))
        app.setFont(app_font(10.5 * scale))
        self._key = key
        self._scale = scale
        self.theme_changed.emit(key)
        # 自定义绘制控件（开关、切换器、印章）需要主动重绘
        for widget in app.allWidgets():
            try:
                widget.update()
            except RuntimeError:
                continue
        return key


_controller: Optional[LiteraryTheme] = None


def controller() -> LiteraryTheme:
    global _controller
    if _controller is None:
        _controller = LiteraryTheme()
    return _controller


def current_theme() -> str:
    return controller().key


def current_palette() -> Palette:
    return controller().palette


def current_scale() -> float:
    return controller().scale


def apply_theme(
    app: Optional[QApplication], theme: Optional[str], scale: Optional[float] = None
) -> str:
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("应用主题前必须先创建 QApplication")
    return controller().apply(app, theme, scale)


def install(app: Optional[QApplication] = None, theme: Optional[str] = None) -> str:
    """安装主题并挂上“旧对话框自动修饰”事件过滤器。"""
    app = app or QApplication.instance()
    if app is None:
        raise RuntimeError("安装主题前必须先创建 QApplication")
    key = apply_theme(app, theme or DEFAULT_THEME)
    from .skin import install_dialog_skin

    install_dialog_skin(app)
    return key


__all__ = [
    "LiteraryTheme",
    "apply_theme",
    "controller",
    "current_palette",
    "current_scale",
    "current_theme",
    "install",
]
