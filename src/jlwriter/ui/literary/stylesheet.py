"""把主题令牌编译成一份完整的 QSS。

只使用 Qt 支持的属性（不用 box-shadow / transition / CSS 变量），
并通过 ``string.Template`` 注入颜色与资源路径，避免 f-string 与 QSS 花括号冲突。
"""
from __future__ import annotations

import re
from string import Template
from typing import Dict

from .themes import METRICS, Palette, kai_family, mono_family, serif_family

_QSS = Template(
    r"""
/* ============================ 基础 ============================ */
QMainWindow, QDialog, QMessageBox, QInputDialog {
    background-color: ${canvas};
    color: ${ink};
}
QDialog {
    background-image: url("${texture}");
}
QWidget {
    color: ${ink};
    selection-background-color: ${selection};
    selection-color: ${selection_text};
}
QWidget:disabled {
    color: ${ink_faint};
}
QToolTip {
    background-color: ${ink};
    color: ${canvas};
    border: 1px solid ${accent};
    padding: 5px 9px;
}

/* ============================ 文本 ============================ */
QLabel {
    background: transparent;
    color: ${ink};
    font-family: "${serif}";
}
QLabel[role="empty-glyph"] {
    font-family: "${serif}";
    font-size: 42px;
    color: ${ink_faint};
    background: transparent;
}
QLabel[role="display"] {
    font-family: "${serif}";
    font-size: 24px;
    font-weight: bold;
    color: ${ink};
}
QLabel[role="title"] {
    font-family: "${serif}";
    font-size: 19px;
    font-weight: bold;
    color: ${ink};
}
QLabel[role="subtitle"] {
    font-family: "${serif}";
    font-size: 13px;
    color: ${ink_muted};
}
QLabel[role="hint"] {
    font-family: "${serif}";
    font-size: 11px;
    color: ${ink_muted};
}
QLabel[role="error"] {
    font-family: "${serif}";
    font-size: 11px;
    color: ${danger};
}
QLabel[role="field-label"] {
    font-family: "${serif}";
    font-size: 12px;
    font-weight: bold;
    color: ${ink_soft};
}
QLabel[role="caption"] {
    font-family: "${serif}";
    font-size: 11px;
    color: ${ink_muted};
}
QLabel[role="motto"] {
    font-family: "${kai}";
    font-size: 12px;
    color: ${ink_muted};
}
QLabel[role="quote"] {
    font-family: "${kai}";
    font-size: 15px;
    color: ${ink_soft};
}
QLabel[role="seal"] {
    font-family: "${serif}";
    font-size: 15px;
    font-weight: bold;
    color: ${accent};
    border: 1px solid ${accent};
    border-radius: 2px;
    background: transparent;
}
QLabel[role="tag"] {
    font-family: "${serif}";
    font-size: 10px;
    color: ${accent_strong};
    background: ${accent_soft};
    border: 1px solid ${line};
    border-radius: 2px;
    padding: 2px 8px;
}
QLabel[role="mono"] {
    font-family: "${mono}";
    font-size: 11px;
    color: ${ink_muted};
}
QLabel[role="cover"] {
    font-family: "${serif}";
    font-size: 12px;
    color: ${ink_faint};
    background-color: ${surface_alt};
    border: 1px dashed ${line_strong};
    border-radius: 3px;
}
QLabel[role="danger"] {
    color: ${danger};
}
QLabel[tone="success"] {
    color: ${success};
}
QLabel[tone="danger"] {
    color: ${danger};
}
QLabel[tone="warning"] {
    color: ${warning};
}
QLabel[tone="muted"] {
    color: ${ink_muted};
}
QLabel[role="score"] {
    font-family: "${serif}";
    font-size: 18px;
    font-weight: bold;
    color: ${ink};
}
QGraphicsView[role="graph"] {
    background-color: ${surface};
    border: 1px solid ${line};
    border-radius: 3px;
}

/* ============================ 按钮 ============================ */
QPushButton {
    font-family: "${serif}";
    font-size: 13px;
    color: ${ink};
    background-color: ${surface_alt};
    border: 1px solid ${line_strong};
    border-radius: ${radius}px;
    padding: 6px 18px;
    min-height: 20px;
}
QPushButton:hover {
    color: ${accent_strong};
    border-color: ${accent};
    background-color: ${surface};
}
QPushButton:pressed {
    background-color: ${accent_soft};
    padding-top: 7px;
    padding-bottom: 5px;
}
QPushButton:focus {
    border-color: ${accent};
}
QPushButton:disabled {
    color: ${ink_faint};
    background-color: ${sunken};
    border-color: ${line};
}
QPushButton[variant="primary"], QPushButton[role="primary"] {
    color: ${on_accent};
    background-color: ${accent};
    border: 1px solid ${accent};
    font-weight: bold;
}
QPushButton[variant="primary"]:hover, QPushButton[role="primary"]:hover {
    background-color: ${accent_strong};
    border-color: ${accent_strong};
    color: ${on_accent};
}
QPushButton[variant="primary"]:pressed, QPushButton[role="primary"]:pressed {
    background-color: ${accent_strong};
}
QPushButton[variant="primary"]:disabled, QPushButton[role="primary"]:disabled {
    color: ${ink_faint};
    background-color: ${sunken};
    border-color: ${line};
}
QPushButton[variant="ghost"], QPushButton[role="ghost"] {
    background: transparent;
    border: 1px solid transparent;
    color: ${ink_soft};
}
QPushButton[variant="ghost"]:hover, QPushButton[role="ghost"]:hover {
    color: ${accent_strong};
    border-color: ${line};
    background: ${surface_alt};
}
QPushButton[variant="danger"], QPushButton[role="danger"] {
    color: ${danger};
    border-color: ${danger};
    background: transparent;
}
QPushButton[variant="danger"]:hover, QPushButton[role="danger"]:hover {
    color: ${on_accent};
    background: ${danger};
    border-color: ${danger};
}
QPushButton[variant="link"] {
    background: transparent;
    border: none;
    color: ${accent};
    padding: 2px 4px;
    text-decoration: underline;
}
QPushButton[variant="link"]:hover {
    color: ${accent_strong};
}

QToolButton {
    font-family: "${serif}";
    font-size: 12px;
    color: ${ink_soft};
    background: transparent;
    border: 1px solid transparent;
    border-radius: ${radius}px;
    padding: 5px 10px;
}
QToolButton:hover {
    color: ${ink};
    background: ${surface_alt};
    border-color: ${line};
}
QToolButton:pressed, QToolButton:checked {
    color: ${accent_strong};
    background: ${accent_soft};
    border-color: ${line};
}
QToolButton[segment="true"] {
    color: ${ink_muted};
    border: none;
    border-radius: 2px;
    padding: 5px 12px;
    min-height: 18px;
}
QToolButton[segment="true"]:hover {
    color: ${ink};
    background: ${surface_alt};
}
QToolButton[segment="true"]:checked {
    color: ${on_accent};
    background: ${accent};
    border: none;
}
QToolButton[segment="true"]:checked:hover {
    background: ${accent_strong};
}
QFrame[role="segmented"] {
    background: ${sunken};
    border: 1px solid ${line};
    border-radius: 3px;
}

/* ============================ 输入 ============================ */
QLineEdit {
    font-family: "${serif}";
    font-size: 13px;
    color: ${ink};
    background-color: ${surface_alt};
    border: 1px solid ${line_strong};
    border-radius: ${radius}px;
    padding: 6px 10px;
    selection-background-color: ${selection};
    selection-color: ${selection_text};
}
/* 正文编辑区不设置字体：编辑器字体由用户设置，QSS 会覆盖 setFont */
QPlainTextEdit, QTextEdit, QTextBrowser {
    color: ${ink};
    background-color: ${surface_alt};
    border: 1px solid ${line_strong};
    border-radius: ${radius}px;
    selection-background-color: ${selection};
    selection-color: ${selection_text};
}
QPlainTextEdit, QTextEdit, QTextBrowser {
    padding: 10px 12px;
}
QTextBrowser#reader {
    background-color: ${surface};
    border: 1px solid ${line};
    padding: 18px 22px;
    font-family: "${serif}";
    font-size: 14px;
}
QTextBrowser#reader QScrollBar:vertical {
    background: transparent;
}
QLineEdit:hover, QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
    border-color: ${ink_faint};
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QTextBrowser:focus,
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {
    border-color: ${accent};
    background-color: ${surface};
}
QLineEdit:disabled, QPlainTextEdit:disabled, QTextEdit:disabled {
    color: ${ink_faint};
    background-color: ${sunken};
    border-color: ${line};
}
QLineEdit[invalid="true"], QPlainTextEdit[invalid="true"] {
    border-color: ${danger};
}
QLineEdit#searchField {
    padding: 7px 10px;
    background: ${surface_alt};
}

QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {
    font-family: "${serif}";
    font-size: 13px;
    color: ${ink};
    background-color: ${surface_alt};
    border: 1px solid ${line_strong};
    border-radius: ${radius}px;
    padding: 6px 10px;
    min-height: 20px;
}
QComboBox::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 26px;
    border: none;
    background: transparent;
}
QComboBox::down-arrow {
    image: url("${chevron}");
    width: 9px;
    height: 6px;
}
QComboBox QAbstractItemView {
    background-color: ${surface};
    color: ${ink};
    border: 1px solid ${line_strong};
    selection-background-color: ${accent_soft};
    selection-color: ${ink};
    outline: 0;
}
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid ${line};
    border-bottom: 1px solid ${line};
    border-top-right-radius: ${radius}px;
    background: ${surface_alt};
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid ${line};
    border-bottom-right-radius: ${radius}px;
    background: ${surface_alt};
}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
    image: url("${chevron_up}");
    width: 8px;
    height: 6px;
}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
    image: url("${chevron}");
    width: 8px;
    height: 6px;
}
QSpinBox::up-button:hover, QSpinBox::down-button:hover,
QDoubleSpinBox::up-button:hover, QDoubleSpinBox::down-button:hover {
    background: ${accent_soft};
}

QCheckBox, QRadioButton {
    font-family: "${serif}";
    font-size: 13px;
    color: ${ink_soft};
    spacing: 8px;
    background: transparent;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
    background-color: ${surface_alt};
    border: 1px solid ${line_strong};
}
QCheckBox::indicator {
    border-radius: 2px;
}
QRadioButton::indicator {
    border-radius: 8px;
}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {
    border-color: ${accent};
}
QCheckBox::indicator:checked {
    background-color: ${accent};
    border-color: ${accent};
    image: url("${check}");
}
QRadioButton::indicator:checked {
    background-color: ${accent};
    border-color: ${accent};
    image: url("${radio}");
}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {
    background-color: ${sunken};
    border-color: ${line};
}

/* ============================ 容器 ============================ */
QFrame[role="card"] {
    background-color: ${surface};
    border: 1px solid ${line};
    border-radius: 3px;
}
QFrame[role="book-card"] {
    background-color: ${surface};
    border: 1px solid ${line};
    border-radius: 4px;
}
QFrame[role="book-card"][hover="true"] {
    background-color: ${surface_alt};
    border: 1px solid ${accent};
}
QFrame[role="preset-card"] {
    background-color: ${surface};
    border: 1px solid ${line};
    border-radius: 4px;
}
QFrame[role="preset-card"][hover="true"] {
    background-color: ${surface_alt};
    border: 1px solid ${accent};
}
QFrame[role="hint-box"] {
    background-color: ${surface_alt};
    border: 1px solid ${line};
    border-left: 3px solid ${accent};
    border-radius: 2px;
}
QFrame[role="hint-box"] QLabel {
    color: ${ink_soft};
    background: transparent;
}
QFrame[role="rule"] {
    background-color: ${line};
    border: none;
    max-height: 1px;
}
QFrame[role="segmented"] {
    background-color: ${sunken};
    border: 1px solid ${line};
    border-radius: 3px;
}
QGroupBox {
    font-family: "${serif}";
    font-size: 13px;
    font-weight: bold;
    color: ${ink_soft};
    border: 1px solid ${line};
    border-radius: 3px;
    margin-top: 14px;
    padding-top: 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: ${ink_soft};
    background-color: ${canvas};
}

/* ============================ 标签页 ============================ */
QTabWidget::pane {
    border: 1px solid ${line};
    border-radius: 3px;
    background-color: ${surface};
    top: -1px;
}
QTabBar::tab {
    font-family: "${serif}";
    font-size: 13px;
    color: ${ink_muted};
    background: transparent;
    padding: 7px 18px;
    border: none;
    border-bottom: 2px solid transparent;
    margin-right: 4px;
}
QTabBar::tab:hover {
    color: ${ink};
}
QTabBar::tab:selected {
    color: ${ink};
    border-bottom: 2px solid ${accent};
}

/* ============================ 列表 / 表格 ============================ */
QListWidget, QTreeWidget, QTableWidget, QListView, QTreeView, QTableView {
    font-family: "${serif}";
    font-size: 13px;
    background-color: ${surface};
    alternate-background-color: ${surface_alt};
    border: 1px solid ${line};
    border-radius: 3px;
    outline: 0;
}
QListWidget::item, QTreeWidget::item {
    padding: 6px 8px;
    border: none;
}
QListWidget::item:hover, QTreeWidget::item:hover {
    background-color: ${surface_alt};
}
QListWidget::item:selected, QTreeWidget::item:selected, QTableWidget::item:selected {
    background-color: ${accent_soft};
    color: ${ink};
}
QTableWidget {
    gridline-color: ${line};
}
QHeaderView::section {
    background-color: ${surface_alt};
    color: ${ink_muted};
    font-family: "${serif}";
    font-size: 11px;
    padding: 6px 8px;
    border: none;
    border-right: 1px solid ${line};
    border-bottom: 1px solid ${line};
}
QTableCornerButton::section {
    background-color: ${surface_alt};
    border: none;
}

/* ============================ 菜单 / 工具栏 ============================ */
QMenuBar {
    background-color: ${canvas};
    color: ${ink_soft};
    border-bottom: 1px solid ${line};
    padding: 2px 4px;
}
QMenuBar::item {
    background: transparent;
    padding: 5px 12px;
    border-radius: 2px;
}
QMenuBar::item:selected {
    color: ${accent_strong};
    background: ${surface_alt};
}
QMenu {
    background-color: ${surface};
    color: ${ink};
    border: 1px solid ${line_strong};
    padding: 6px;
}
QMenu::item {
    padding: 6px 28px 6px 22px;
    border-radius: 2px;
    background: transparent;
}
QMenu::item:selected {
    background-color: ${accent_soft};
    color: ${accent_strong};
}
QMenu::item:disabled {
    color: ${ink_faint};
}
QMenu::separator {
    height: 1px;
    background: ${line};
    margin: 5px 10px;
}
QMenu::indicator {
    width: 14px;
    height: 14px;
}

QToolBar {
    background-color: ${canvas};
    border: none;
    border-bottom: 1px solid ${line};
    spacing: 4px;
    padding: 5px 8px;
}
QToolBar::separator {
    width: 1px;
    background: ${line};
    margin: 6px 8px;
}
QToolBar QLabel {
    color: ${ink_muted};
    font-size: 12px;
    padding: 0 2px;
}

QStatusBar {
    background-color: ${surface};
    color: ${ink_muted};
    border-top: 1px solid ${line};
}
QStatusBar QLabel {
    color: ${ink_muted};
    font-size: 11px;
}

/* ============================ 滚动条 ============================ */
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: ${line_strong};
    min-height: 28px;
    border-radius: 3px;
}
QScrollBar::handle:vertical:hover {
    background: ${accent};
}
QScrollBar:horizontal {
    background: transparent;
    height: 10px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: ${line_strong};
    min-width: 28px;
    border-radius: 3px;
}
QScrollBar::handle:horizontal:hover {
    background: ${accent};
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
    background: none;
    border: none;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
QAbstractScrollArea::corner {
    background: transparent;
}

/* ============================ 其他 ============================ */
QSplitter::handle {
    background-color: ${line};
}
QSplitter::handle:hover {
    background-color: ${accent};
}
QSlider::groove:horizontal {
    height: 2px;
    background: ${line_strong};
    border-radius: 1px;
}
QSlider::sub-page:horizontal {
    background: ${accent};
}
QSlider::handle:horizontal {
    width: 12px;
    margin: -5px 0;
    border-radius: 6px;
    background: ${accent};
    border: 2px solid ${canvas};
}
QProgressBar {
    background: ${sunken};
    border: 1px solid ${line};
    border-radius: 2px;
    height: 6px;
    text-align: center;
    color: ${ink_muted};
}
QProgressBar::chunk {
    background: ${accent};
    border-radius: 1px;
}
QDialogButtonBox QPushButton {
    min-width: 88px;
}
QMessageBox QLabel {
    color: ${ink};
    background: transparent;
}
QMessageBox QPushButton {
    min-width: 84px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
"""
)


def build_qss(palette: Palette, assets: Dict[str, str], scale: float = 1.0) -> str:
    """渲染主题 QSS。``scale`` 统一缩放所有 px（字号/留白/边框）。"""
    values = {
        "serif": serif_family(),
        "kai": kai_family(),
        "mono": mono_family(),
        "radius": METRICS.radius,
        "check": assets["check"],
        "radio": assets["radio"],
        "chevron": assets["chevron"],
        "chevron_up": assets["chevron_up"],
        "search": assets["search"],
        "texture": assets["texture"],
    }
    for field_name in palette.__dataclass_fields__:
        value = getattr(palette, field_name)
        if isinstance(value, str) and value.startswith("#"):
            values[field_name] = value
    qss = _QSS.substitute(values)
    if abs(scale - 1.0) > 0.01:
        qss = re.sub(r"(?<![\w.])(\d+(?:\.\d+)?)px", _px_scaler(scale), qss)
    return qss


def _px_scaler(scale: float):
    def repl(match: "re.Match[str]") -> str:
        value = float(match.group(1))
        if value <= 0:
            return "0px"
        return f"{max(1, int(round(value * scale)))}px"

    return repl
