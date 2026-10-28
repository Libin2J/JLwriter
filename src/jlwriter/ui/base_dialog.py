"""统一对话框基类：题头 + 内容 + 页脚。

实现已迁移到文学风设计系统 :mod:`jlwriter.ui.literary`，但保留原有子类使用的
全部 API（``build_content`` / ``build_buttons`` / ``build_footer`` / ``add_button``），
因此十几个旧对话框无需改动即可获得新外观。

新代码建议直接继承 :class:`jlwriter.ui.literary.FramedDialog`。
"""
from __future__ import annotations

from PyQt5.QtWidgets import QApplication

from .literary.widgets import FramedDialog, LiteraryButton


class BaseDialog(FramedDialog):
    def __init__(
        self,
        parent=None,
        title="",
        subtitle="",
        default_size=(640, 480),
        min_size=(480, 360),
        show_header=True,
        show_button_bar=True,
        seal_text="墨",
        scroll_body=True,
    ):
        super().__init__(
            parent,
            title=title,
            subtitle=subtitle,
            seal_text=seal_text,
            show_header=show_header,
            scroll_body=scroll_body,
        )
        self.resize(*default_size)
        self.setMinimumSize(*min_size)
        self._user_moved = False

        # 兼容旧代码里的内部名字
        self._content = self._body
        self._content_layout = self.content_layout

        self.build_content(self._content_layout)

        if show_button_bar:
            self.build_buttons(self.footer_layout)

        self.build_footer(self._root)

    # -------- 子类覆写点 --------
    def build_content(self, layout):
        """子类往 layout 中添加内容。"""

    def build_buttons(self, layout):
        """默认提供 取消 / 确定。"""
        self.add_button(layout, "取消", self.reject)
        self.add_button(
            layout, "确定", self.accept, role="primary", default=True
        )

    def build_footer(self, root_layout):
        """子类覆写后可向 root_layout 追加底部控件。"""

    # -------- 工具 --------
    def add_button(
        self, layout, text, slot, role="normal", default=False
    ) -> LiteraryButton:
        variant = {
            "primary": "primary",
            "danger": "danger",
            "ghost": "ghost",
            "normal": "quiet",
            "quiet": "quiet",
            "link": "link",
        }.get(role, "quiet")
        button = LiteraryButton(text, variant=variant)
        if default:
            button.setDefault(True)
            button.setAutoDefault(True)
        button.clicked.connect(slot)
        layout.addWidget(button)
        return button

    # -------- 尺寸与居中 --------
    def showEvent(self, event):
        super().showEvent(event)
        from .literary.skin import fit_dialog_to_screen

        fit_dialog_to_screen(self)

        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        available = screen.availableGeometry()
        if not getattr(self, "_user_moved", False):
            x = available.x() + (available.width() - self.width()) // 2
            y = available.y() + (available.height() - self.height()) // 2
            self.move(x, y)

    def moveEvent(self, event):
        if event.spontaneous():
            self._user_moved = True
        super().moveEvent(event)
