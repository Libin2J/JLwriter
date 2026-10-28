"""让旧版对话框自动获得新皮肤。

主程序里有二十多个 ``QDialog`` 子类，逐个改写风险高。这里用应用级事件过滤器，
在对话框显示前统一补上纸纹属性、按钮层级与 Windows 深色标题栏；控件本身仍由
全局 QSS 负责。新的对话框继续使用 :class:`FramedDialog` 即可获得完整题头。
"""
from __future__ import annotations

import sys
from typing import Optional

from PyQt5.QtCore import QEvent, QObject, Qt
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .controller import controller, current_palette
from .widgets import DialogHeader, FramedDialog, repolish

_PRIMARY_PREFIXES = (
    "保存",
    "确定",
    "确认",
    "导出",
    "生成",
    "开始",
    "应用",
    "继续",
    "打开",
    "ok",
    "yes",
)
_DANGER_PREFIXES = ("删除", "移除", "清空", "delete", "remove")

# 不依赖 Qt 翻译文件：标准按钮统一成中文，避免出现 Yes / No / OK
_STANDARD_BUTTON_TEXTS = {
    "Ok": "确定",
    "Open": "打开",
    "Save": "保存",
    "Cancel": "取消",
    "Close": "关闭",
    "Discard": "放弃",
    "Apply": "应用",
    "Reset": "重置",
    "RestoreDefaults": "恢复默认",
    "Help": "帮助",
    "Yes": "是",
    "YesToAll": "全部是",
    "No": "否",
    "NoToAll": "全部否",
    "Abort": "中止",
    "Retry": "重试",
    "Ignore": "忽略",
}


def _tone_for_text(text: str) -> Optional[str]:
    value = (text or "").strip().lower()
    if not value:
        return None
    if any(value.startswith(prefix) for prefix in _DANGER_PREFIXES):
        return "danger"
    if any(value.startswith(prefix) for prefix in _PRIMARY_PREFIXES):
        return "primary"
    return None


def _is_dark() -> bool:
    return current_palette().key == "night"


def _set_dark_title_bar(widget: QWidget, dark: bool) -> None:
    """Windows 10/11：让原生标题栏跟随夜读主题。失败静默。"""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes

        hwnd = int(widget.winId())
        value = ctypes.c_int(1 if dark else 0)
        dwmapi = ctypes.windll.dwmapi
        # 20 = DWMWA_USE_IMMERSIVE_DARK_MODE（Win10 20H1+），19 为旧版本
        for attribute in (20, 19):
            result = dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                ctypes.c_uint(attribute),
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
            if result == 0:
                break
    except Exception:
        pass


def _maybe_add_header(dialog: QDialog) -> None:
    """给“裸 QDialog”自动补一个题头，避免只有纸纹没有标题。"""
    if isinstance(dialog, (FramedDialog, QMessageBox, QInputDialog)):
        return
    if dialog.property("_literaryHeader"):
        return
    layout = dialog.layout()
    if not isinstance(layout, QVBoxLayout) or layout.count() == 0:
        return
    title = (dialog.windowTitle() or "").strip()
    if not title:
        return

    header = DialogHeader(title, seal_text="墨")
    layout.insertWidget(0, header)
    layout.setContentsMargins(30, 22, 30, 22)
    layout.setSpacing(14)
    dialog.setProperty("_literaryHeader", True)


def fit_dialog_to_screen(dialog: QDialog) -> None:
    """把对话框限制在可用桌面内，并保证标题栏留在屏幕里。

    逻辑分辨率 1280×800（200% 缩放的 2560×1600）是常见笔记本形态，
    旧对话框默认 1680×1280 会直接顶出屏幕；这里统一按 94%×90% 收缩。
    """
    screen = dialog.screen() or QApplication.primaryScreen()
    if screen is None:
        return
    available = screen.availableGeometry()
    max_w = max(480, int(available.width() * 0.94))
    max_h = max(360, int(available.height() * 0.90))

    if dialog.minimumWidth() > max_w:
        dialog.setMinimumWidth(max_w)
    if dialog.minimumHeight() > max_h:
        dialog.setMinimumHeight(max_h)

    width = min(dialog.width(), max_w)
    height = min(dialog.height(), max_h)
    if (width, height) != (dialog.width(), dialog.height()):
        dialog.resize(width, height)

    frame = dialog.frameGeometry()
    max_x = available.x() + max(0, available.width() - frame.width())
    max_y = available.y() + max(0, available.height() - frame.height())
    x = min(max(frame.x(), available.x()), max_x)
    y = min(max(frame.y(), available.y()), max_y)
    if (x, y) != (frame.x(), frame.y()):
        dialog.move(x, y)


def polish_dialog(dialog: QDialog) -> None:
    """给任意对话框补齐主题属性与按钮层级。"""
    dialog.setProperty("literary", True)
    dialog.setAttribute(Qt.WA_StyledBackground, True)
    _maybe_add_header(dialog)
    fit_dialog_to_screen(dialog)

    if isinstance(dialog, QMessageBox):
        dialog.setMinimumWidth(420)
        if dialog.width() < 420:
            dialog.resize(420, max(dialog.height(), 120))
        for role_name, text in _STANDARD_BUTTON_TEXTS.items():
            role = getattr(QMessageBox, role_name, None)
            if role is None:
                continue
            button = dialog.button(role)
            if button is not None:
                button.setText(text)
        primary = (
            dialog.button(QMessageBox.Ok)
            or dialog.button(QMessageBox.Yes)
            or dialog.button(QMessageBox.Save)
        )
        if primary is not None:
            primary.setProperty("variant", "primary")
            primary.setMinimumWidth(88)
            repolish(primary)

    for box in dialog.findChildren(QDialogButtonBox):
        for role_name, text in _STANDARD_BUTTON_TEXTS.items():
            role = getattr(QDialogButtonBox, role_name, None)
            if role is None:
                continue
            button = box.button(role)
            if button is not None:
                button.setText(text)
        for button in box.buttons():
            if button.property("variant"):
                continue
            tone = _tone_for_text(button.text())
            if tone:
                button.setProperty("variant", tone)
                repolish(button)

    # 旧代码直接放的 QPushButton（没有 QDialogButtonBox）
    if not dialog.findChildren(QDialogButtonBox):
        for button in dialog.findChildren(QPushButton):
            tone = _tone_for_text(button.text())
            if tone:
                button.setProperty("variant", tone)
                button.setMinimumWidth(88)
                repolish(button)

    _set_dark_title_bar(dialog, _is_dark())


class _DialogSkinFilter(QObject):
    def eventFilter(self, obj, event):  # noqa: N802
        if event.type() == QEvent.Show and isinstance(obj, QDialog):
            polish_dialog(obj)
        return False


_filter: Optional[_DialogSkinFilter] = None


def install_dialog_skin(app: Optional[QApplication] = None) -> None:
    """安装一次即可；重复调用无副作用。"""
    global _filter
    app = app or QApplication.instance()
    if app is None or app.property("_literary_skin_installed"):
        return
    _filter = _DialogSkinFilter(app)
    app.installEventFilter(_filter)
    app.setProperty("_literary_skin_installed", True)

    # 主题切换时同步已打开窗口的标题栏
    def _refresh_titles(key: str) -> None:
        for widget in app.topLevelWidgets():
            if isinstance(widget, QWidget):
                _set_dark_title_bar(widget, key == "night")

    controller().theme_changed.connect(_refresh_titles)
