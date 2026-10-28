"""可移植的文学风控件。

这些控件只依赖 PyQt5 与 :mod:`jlwriter.ui.literary` 的主题令牌，不引用主程序
任何业务对象，因此可以整体复制到别的 PyQt 项目：

    from jlwriter.ui.literary import apply_theme, FramedDialog, Field, LiteraryButton

控件清单
--------
* :class:`LiteraryDialog` — 带纸纹与顶部饰线的对话框基类（可直接替换 QDialog）
* :class:`FramedDialog` — 标准“题头 + 内容 + 页脚”对话框
* :class:`DialogHeader` / :class:`Ornament` / :class:`Seal` — 题头、云纹分隔、印章
* :class:`LiteraryButton` / :class:`Field` / :class:`SearchField` — 按钮与输入
* :class:`ToggleSwitch` / :class:`ThemeSwitcher` — 开关与三主题切换器
* :class:`Card` / :class:`Tag` / :class:`EmptyState` — 容器与空状态
"""
from __future__ import annotations

from typing import Optional

from PyQt5.QtCore import (
    QEasingCurve,
    QPointF,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QAbstractButton,
    QComboBox,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .assets import theme_glyph
from .controller import current_palette, current_theme
from .themes import METRICS, Palette, serif_family

# 供外部设置角色时避免拼写错误
ROLE_TITLE = "title"
ROLE_SUBTITLE = "subtitle"
ROLE_HINT = "hint"
ROLE_FIELD = "field-label"


def repolish(widget: QWidget) -> None:
    """属性变化后重新应用 QSS。"""
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


class Seal(QLabel):
    """朱砂/暖金小印章，用于题头右侧。"""

    def __init__(self, text: str = "墨", size: int = 42, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setProperty("role", "seal")
        self.setAlignment(Qt.AlignCenter)
        self.setFixedSize(size, size)
        self.setToolTip(text)


class Ornament(QWidget):
    """一条两端收细、中间带菱形的分隔饰线。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setFixedHeight(14)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def paintEvent(self, event) -> None:  # noqa: N802 - Qt 命名
        palette = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        center = width / 2
        y = self.height() / 2

        gradient = QLinearGradient(0, 0, width, 0)
        line = QColor(palette.line_strong)
        transparent = QColor(line)
        transparent.setAlpha(0)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.18, line)
        gradient.setColorAt(0.45, line)
        gradient.setColorAt(0.55, line)
        gradient.setColorAt(0.82, line)
        gradient.setColorAt(1.0, transparent)
        painter.setPen(QPen(gradient, 1))
        painter.drawLine(QPointF(0, y), QPointF(center - 16, y))
        painter.drawLine(QPointF(center + 16, y), QPointF(width, y))

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(palette.accent))
        painter.save()
        painter.translate(center, y)
        painter.rotate(45)
        painter.drawRect(QRectF(-3.2, -3.2, 6.4, 6.4))
        painter.restore()
        painter.setBrush(QColor(palette.line_strong))
        painter.drawEllipse(QPointF(center - 11, y), 1.2, 1.2)
        painter.drawEllipse(QPointF(center + 11, y), 1.2, 1.2)
        painter.end()


class DialogHeader(QWidget):
    """题头：宋体大标题 + 副题 + 印章 + 饰线。"""

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        seal_text: str = "墨",
        motto: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        row = QHBoxLayout()
        row.setSpacing(14)
        text_col = QVBoxLayout()
        text_col.setSpacing(3)

        self.title_label = QLabel(title)
        self.title_label.setProperty("role", "title")
        self.title_label.setWordWrap(True)
        self.title_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        text_col.addWidget(self.title_label)

        self.subtitle_label = QLabel(subtitle)
        self.subtitle_label.setProperty("role", "subtitle")
        self.subtitle_label.setWordWrap(True)
        self.subtitle_label.setVisible(bool(subtitle))
        text_col.addWidget(self.subtitle_label)

        if motto:
            motto_label = QLabel(motto)
            motto_label.setProperty("role", "motto")
            text_col.addWidget(motto_label)

        row.addLayout(text_col, 1)
        self.seal = Seal(seal_text or "墨")
        row.addWidget(self.seal, 0, Qt.AlignTop)
        root.addLayout(row)
        root.addWidget(Ornament())

    def set_subtitle(self, text: str) -> None:
        self.subtitle_label.setText(text)
        self.subtitle_label.setVisible(bool(text))


class LiteraryDialog(QDialog):
    """QDialog 的文学风替代品：纸纹、顶部饰线、主题字体。

    不创建任何布局，因此可以一行替换现有 ``QDialog`` 子类而不用改布局代码。
    """

    def __init__(self, parent: Optional[QWidget] = None, title: str = ""):
        super().__init__(parent)
        self.setProperty("literary", True)
        self.setAttribute(Qt.WA_StyledBackground, True)
        if title:
            self.setWindowTitle(title)

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        palette = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width = self.width()
        if width > 96:
            inset = 26
            pen = QPen(QColor(palette.accent))
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.drawLine(QPointF(inset, 0.5), QPointF(width / 2 - 9, 0.5))
            painter.drawLine(QPointF(width / 2 + 9, 0.5), QPointF(width - inset, 0.5))
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(palette.accent))
            painter.save()
            painter.translate(width / 2, 1)
            painter.rotate(45)
            painter.drawRect(QRectF(-3, -3, 6, 6))
            painter.restore()
        painter.end()


class FramedDialog(LiteraryDialog):
    """标准对话框骨架：题头 / 内容 / 页脚。"""

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        title: str = "",
        subtitle: str = "",
        seal_text: str = "墨",
        motto: str = "",
        margins=None,
        spacing: int = METRICS.section_gap,
        show_header: bool = True,
        scroll_body: bool = True,
    ):
        super().__init__(parent, title)
        left, top, right, bottom = margins or (
            METRICS.page_margin_x,
            METRICS.page_margin_top,
            METRICS.page_margin_x,
            METRICS.page_margin_bottom,
        )
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(left, top, right, bottom)
        self._root.setSpacing(spacing)

        self.header: Optional[DialogHeader] = None
        if show_header and (title or subtitle):
            self.header = DialogHeader(title, subtitle, seal_text, motto)
            self._root.addWidget(self.header)

        self._body = QWidget()
        self._body.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(14)

        # 正文区放进滚动容器：复杂对话框在 1280×800 这类屏幕上也只出现滚动条，
        # 而不是把窗口顶出屏幕。自带独立滚动区的档案类页面可关闭该行为，
        # 让左侧列表拥有自己的滚动条。
        self._body_scroll: Optional[QScrollArea] = None
        if scroll_body:
            self._body_scroll = QScrollArea()
            self._body_scroll.setWidgetResizable(True)
            self._body_scroll.setFrameShape(QFrame.NoFrame)
            self._body_scroll.setWidget(self._body)
            self._body_scroll.viewport().setAutoFillBackground(False)
            self._root.addWidget(self._body_scroll, 1)
        else:
            self._root.addWidget(self._body, 1)

        self._footer = QHBoxLayout()
        self._footer.setContentsMargins(0, 6, 0, 0)
        self._footer.setSpacing(10)
        self._footer.addStretch(1)
        self._root.addLayout(self._footer)

        # 便于旧代码/新代码共用
        self.content_layout = self._body_layout
        self.footer_layout = self._footer

    # ---- 便捷 API ----
    def set_subtitle(self, text: str) -> None:
        if self.header:
            self.header.set_subtitle(text)

    def add_button(
        self,
        text: str,
        slot=None,
        *,
        variant: str = "quiet",
        default: bool = False,
    ) -> "LiteraryButton":
        button = LiteraryButton(text, variant=variant)
        if default:
            button.setDefault(True)
            button.setAutoDefault(True)
        if slot is not None:
            button.clicked.connect(slot)
        self._footer.addWidget(button)
        return button

    def add_footer_widget(self, widget: QWidget) -> None:
        self._footer.insertWidget(0, widget)

    def add_body(self, widget: QWidget, stretch: int = 0) -> None:
        self._body_layout.addWidget(widget, stretch)

    def add_body_layout(self, layout) -> None:
        self._body_layout.addLayout(layout)


class LiteraryButton(QPushButton):
    """统一高度与字体的按钮；``variant`` 支持 primary / quiet / ghost / danger / link。"""

    VARIANTS = ("primary", "quiet", "ghost", "danger", "link")

    def __init__(
        self,
        text: str = "",
        *,
        variant: str = "quiet",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(METRICS.button_height if variant != "link" else 20)
        self.set_variant(variant)
        try:
            self.setFont(QFont(serif_family(), 10))
        except Exception:
            pass

    def set_variant(self, variant: str) -> None:
        variant = variant if variant in self.VARIANTS else "quiet"
        self.setProperty("variant", variant)
        repolish(self)


class LiteraryCloseButton(QAbstractButton):
    """自绘的“×”关闭按钮。

    之前用 ``QPushButton("✕")``，而界面字体是宋体，缺字时只剩一个方框；
    这里直接用 QPainter 画两条线，任何字体/缩放下都能辨认。
    基于 QAbstractButton 而不是 QPushButton，避免样式表的 min-height
    把固定尺寸压扁（那会让 × 变成一条横线）。
    """

    def __init__(
        self,
        tooltip: str = "关闭",
        size: int = 28,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(size, size)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self.setAccessibleName(tooltip)
        self.setFocusPolicy(Qt.StrongFocus)
        self._hover = False

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._size, self._size)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._size, self._size)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):  # noqa: N802
        palette = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self._hover or self.isDown():
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(palette.accent_soft))
            painter.drawRoundedRect(rect, 3, 3)

        color = QColor(palette.accent_strong if self._hover else palette.ink_muted)
        pen = QPen(color, 1.6)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        inset = self.width() * 0.32
        painter.drawLine(
            QPointF(inset, inset),
            QPointF(self.width() - inset, self.height() - inset),
        )
        painter.drawLine(
            QPointF(self.width() - inset, inset),
            QPointF(inset, self.height() - inset),
        )

        if self.hasFocus():
            painter.setPen(QPen(QColor(palette.accent_soft), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(rect, 3, 3)
        painter.end()


class Field(QWidget):
    """带题签、说明与错误态的输入字段。

    用法::

        field = Field("书名", placeholder="请输入书名", required=True)
        layout.addWidget(field)
        field.editor.text()
    """

    def __init__(
        self,
        label: str,
        editor: Optional[QWidget] = None,
        *,
        hint: str = "",
        required: bool = False,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(METRICS.field_gap)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self.label = QLabel(label)
        self.label.setProperty("role", "field-label")
        head.addWidget(self.label)
        if required:
            star = QLabel("·")
            star.setProperty("role", "error")
            head.addWidget(star)
        head.addStretch(1)
        self.hint_label = QLabel(hint)
        self.hint_label.setProperty("role", "hint")
        self.hint_label.setVisible(bool(hint))
        head.addWidget(self.hint_label)
        root.addLayout(head)

        self.editor = editor or QLineEdit()
        root.addWidget(self.editor)

        self.helper = QLabel("")
        self.helper.setProperty("role", "hint")
        self.helper.setWordWrap(True)
        self.helper.setVisible(False)
        root.addWidget(self.helper)

    def value(self) -> str:
        if isinstance(self.editor, QLineEdit):
            return self.editor.text()
        try:
            return self.editor.toPlainText()
        except Exception:
            return ""

    def set_value(self, text: str) -> None:
        if isinstance(self.editor, QLineEdit):
            self.editor.setText(text)
        else:
            try:
                self.editor.setPlainText(text)
            except Exception:
                pass

    def set_error(self, message: str) -> None:
        self.helper.setProperty("role", "error")
        self.helper.setText(message)
        self.helper.setVisible(True)
        self.editor.setProperty("invalid", True)
        repolish(self.helper)
        repolish(self.editor)

    def clear_error(self) -> None:
        self.helper.clear()
        self.helper.setVisible(False)
        self.editor.setProperty("invalid", False)
        repolish(self.editor)


class SearchField(QLineEdit):
    """带放大镜与清除按钮的搜索框。"""

    def __init__(self, placeholder: str = "搜索…", parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setObjectName("searchField")
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumHeight(32)
        self._refresh_icon()

    def _refresh_icon(self) -> None:
        from .assets import ensure_assets

        palette = current_palette()
        icon_path = ensure_assets(palette)["search"]
        self._search_action = self.addAction(QIcon(icon_path), QLineEdit.LeadingPosition)

    def changeEvent(self, event) -> None:  # noqa: N802
        super().changeEvent(event)
        if event.type() == event.StyleChange and hasattr(self, "_search_action"):
            self.removeAction(self._search_action)
            self._refresh_icon()


class LiteraryComboBox(QComboBox):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(32)
        self.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.setMinimumContentsLength(12)


class ToggleSwitch(QAbstractButton):
    """墨色胶囊开关，带 180ms 滑动动画。"""

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pos = 0.0
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(METRICS.animation_ms)
        self._animation.setEasingCurve(QEasingCurve.InOutCubic)
        self._animation.valueChanged.connect(self._on_animated)
        self.toggled.connect(self._animate_to_state)

    def _on_animated(self, value) -> None:
        self._pos = float(value)
        self.update()

    def _animate_to_state(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(self._pos)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 22)

    def minimumSizeHint(self) -> QSize:  # noqa: N802
        return QSize(40, 22)

    def paintEvent(self, event) -> None:  # noqa: N802
        palette = current_palette()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        radius = rect.height() / 2

        off = QColor(palette.line_strong)
        on = QColor(palette.accent)
        track = QColor(
            int(off.red() + (on.red() - off.red()) * self._pos),
            int(off.green() + (on.green() - off.green()) * self._pos),
            int(off.blue() + (on.blue() - off.blue()) * self._pos),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(track)
        painter.drawRoundedRect(rect, radius, radius)

        knob_d = rect.height() - 4
        x = rect.x() + 2 + (rect.width() - knob_d - 4) * self._pos
        painter.setBrush(QColor(palette.on_accent if self.isChecked() else palette.surface_alt))
        painter.setPen(QPen(QColor(palette.line), 1))
        painter.drawEllipse(QRectF(x, rect.y() + 2, knob_d, knob_d))
        if self.hasFocus():
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(QColor(palette.accent), 1, Qt.DotLine))
            painter.drawRoundedRect(rect.adjusted(-1, -1, 1, 1), radius, radius)
        painter.end()


class ThemeSwitcher(QFrame):
    """夜读 / 护眼 / 书卷 三段式切换器。

    只发出 ``theme_changed`` 信号，由主窗口决定是否应用与持久化，避免控件
    直接依赖业务配置。
    """

    theme_changed = pyqtSignal(str)

    def __init__(self, current: Optional[str] = None, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setProperty("role", "segmented")
        self.setFixedHeight(30)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 2, 3, 2)
        layout.setSpacing(0)

        self._buttons = {}
        for key, name, _ in self._choices():
            button = QToolButton()
            button.setProperty("segment", True)
            button.setText(name)
            button.setCheckable(True)
            button.setAutoExclusive(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setIconSize(QSize(14, 14))
            button.clicked.connect(lambda _checked=False, k=key: self._on_clicked(k))
            layout.addWidget(button)
            self._buttons[key] = button

        self._refresh_icons()
        self.set_current(current or current_theme())

        from .controller import controller

        controller().theme_changed.connect(self._on_theme_changed)

    @staticmethod
    def _choices():
        from .themes import theme_choices

        return theme_choices()

    def _on_clicked(self, key: str) -> None:
        self.set_current(key)
        self.theme_changed.emit(key)

    def _on_theme_changed(self, key: str) -> None:
        self._refresh_icons()
        self.set_current(key)

    def set_current(self, key: str) -> None:
        from .themes import normalize_theme

        key = normalize_theme(key)
        button = self._buttons.get(key)
        if button is None:
            return
        for other in self._buttons.values():
            other.blockSignals(True)
            other.setChecked(other is button)
            other.blockSignals(False)

    def _refresh_icons(self) -> None:
        from .assets import theme_glyph

        palette = current_palette()
        for key, button in self._buttons.items():
            normal = theme_glyph(palette, key)
            painter_palette = _glyph_on_accent(palette, key)
            icon = QIcon()
            icon.addPixmap(normal, QIcon.Normal, QIcon.Off)
            icon.addPixmap(painter_palette, QIcon.Normal, QIcon.On)
            icon.addPixmap(painter_palette, QIcon.Selected, QIcon.On)
            button.setIcon(icon)


def _glyph_on_accent(palette: Palette, key: str) -> QPixmap:
    """在选中态（强调色底）上重绘一份纸色图标。"""
    size = 14
    pixmap = theme_glyph(palette, key, size)
    tinted = QPixmap(pixmap.size())
    tinted.fill(Qt.transparent)
    painter = QPainter(tinted)
    painter.drawPixmap(0, 0, pixmap)
    painter.setCompositionMode(QPainter.CompositionMode_SourceIn)
    painter.fillRect(tinted.rect(), QColor(palette.on_accent))
    painter.end()
    return tinted


class Card(QFrame):
    """纸卡片容器。"""

    def __init__(
        self,
        title: str = "",
        *,
        hint: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setProperty("role", "card")
        self.body = QVBoxLayout(self)
        self.body.setContentsMargins(16, 14, 16, 14)
        self.body.setSpacing(8)
        if title:
            label = QLabel(title)
            label.setProperty("role", "subtitle")
            self.body.addWidget(label)
        if hint:
            hint_label = QLabel(hint)
            hint_label.setProperty("role", "hint")
            hint_label.setWordWrap(True)
            self.body.addWidget(hint_label)


class Tag(QLabel):
    def __init__(self, text: str, parent: Optional[QWidget] = None):
        super().__init__(text, parent)
        self.setProperty("role", "tag")
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)


class EmptyState(QWidget):
    """空状态：一个大字印章 + 一句题词。"""

    def __init__(
        self,
        title: str,
        hint: str = "",
        glyph: str = "空",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 28, 24, 28)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)

        seal = QLabel(glyph)
        seal.setAlignment(Qt.AlignCenter)
        seal.setFixedSize(52, 52)
        seal.setProperty("role", "seal")
        seal.setFont(QFont(serif_family(), 20, QFont.Bold))
        layout.addWidget(seal, 0, Qt.AlignHCenter)

        title_label = QLabel(title)
        title_label.setProperty("role", "subtitle")
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        if hint:
            hint_label = QLabel(hint)
            hint_label.setProperty("role", "hint")
            hint_label.setAlignment(Qt.AlignCenter)
            hint_label.setWordWrap(True)
            layout.addWidget(hint_label)


__all__ = [
    "Card",
    "DialogHeader",
    "EmptyState",
    "Field",
    "FramedDialog",
    "LiteraryButton",
    "LiteraryComboBox",
    "LiteraryDialog",
    "Ornament",
    "SearchField",
    "Seal",
    "Tag",
    "ThemeSwitcher",
    "ToggleSwitch",
    "repolish",
]
