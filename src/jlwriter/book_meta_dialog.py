"""
书籍信息对话框：支持新建与编辑两种模式

- 新建模式（book_dir=None）：填入书名/作者/简介/封面后，点“保存”时创建书籍目录
- 编辑模式（book_dir=路径）：修改现有书籍的元数据

视觉：书卷式“左题签 / 右封面”版式，输入与校验由文学风控件统一提供。
"""
import json
import os

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from . import book_manager as bm
from .ui.literary import Field, FramedDialog, LiteraryButton


class BookMetaDialog(FramedDialog):
    def __init__(self, book_dir=None, parent=None):
        self.book_dir = book_dir
        self.is_new = book_dir is None
        self._pending_cover_path = None

        if self.is_new:
            self.meta = {
                "title": "",
                "description": "",
                "cover": "",
                "created_at": "",
                "updated_at": "",
                "author": "",
            }
            title = "新建书籍"
            subtitle = "题签 · 为这本书写下名字"
        else:
            self.meta = bm.load_meta(book_dir)
            title = "编辑书籍信息"
            subtitle = "题签 · 修改书名、作者与封面"

        super().__init__(
            parent,
            title=title,
            subtitle=subtitle,
            seal_text="藏",
            motto="一书一世界，一名一浮生",
        )
        self.resize(760, 640)
        self.setMinimumSize(560, 500)

        body = QHBoxLayout()
        body.setSpacing(26)

        form = QVBoxLayout()
        form.setSpacing(14)

        self.title_field = Field(
            "书名", hint="必填", required=True
        )
        self.title_edit = self.title_field.editor
        self.title_edit.setMaxLength(60)
        self.title_edit.textChanged.connect(self.title_field.clear_error)

        self.author_field = Field("作者", hint="可选")
        self.author_edit = self.author_field.editor
        self.author_edit.setMaxLength(40)

        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setMinimumHeight(150)
        self.desc_edit.setPlaceholderText("用一两句话介绍这本书的气质与故事……")
        self.desc_field = Field(
            "简介", editor=self.desc_edit, hint="展示在书架上"
        )

        form.addWidget(self.title_field)
        form.addWidget(self.author_field)
        form.addWidget(self.desc_field, 1)
        body.addLayout(form, 1)

        # ---- 封面 ----
        cover_col = QVBoxLayout()
        cover_col.setSpacing(10)
        cover_title = QLabel("封面")
        cover_title.setProperty("role", "field-label")
        cover_col.addWidget(cover_title)

        self.cover_preview = QLabel("暂无封面")
        self.cover_preview.setProperty("role", "cover")
        self.cover_preview.setFixedSize(132, 190)
        self.cover_preview.setAlignment(Qt.AlignCenter)
        self.cover_preview.setWordWrap(True)
        cover_col.addWidget(self.cover_preview)

        self.cover_button = LiteraryButton("选择图片", variant="quiet")
        self.cover_button.clicked.connect(self._choose_cover)
        cover_col.addWidget(self.cover_button)

        self.remove_cover_button = LiteraryButton("移除封面", variant="ghost")
        self.remove_cover_button.clicked.connect(self._remove_cover)
        cover_col.addWidget(self.remove_cover_button)
        cover_col.addStretch(1)
        cover_hint = QLabel("建议 3:4 竖图\nPNG / JPG")
        cover_hint.setProperty("role", "hint")
        cover_col.addWidget(cover_hint, alignment=Qt.AlignLeft)
        body.addLayout(cover_col, 0)

        body_widget = QWidget()
        body_widget.setLayout(body)
        self.add_body(body_widget, 1)

        self._load_cover_preview()
        self._fill_form()

        self.add_button("取消", self.reject, variant="ghost")
        self.add_button("保存", self._save, variant="primary", default=True)

    # ============================================================
    # 表单
    # ============================================================
    def _fill_form(self):
        self.title_edit.setText(self.meta.get("title", ""))
        self.author_edit.setText(self.meta.get("author", ""))
        self.desc_edit.setPlainText(self.meta.get("description", ""))
        if not self.is_new:
            self.title_edit.setPlaceholderText("请输入书名（必填）")
        else:
            self.title_edit.setPlaceholderText("例如：长夜将明")
        self.author_edit.setPlaceholderText("可选")

    # ============================================================
    # 封面
    # ============================================================
    def _cover_path(self):
        if self._pending_cover_path:
            return self._pending_cover_path
        if not self.is_new:
            return bm.get_cover_path(self.book_dir)
        return None

    def _load_cover_preview(self):
        path = self._cover_path()
        if path:
            pix = QPixmap(path)
            if not pix.isNull():
                self.cover_preview.setPixmap(
                    pix.scaled(
                        132,
                        190,
                        Qt.KeepAspectRatio,
                        Qt.SmoothTransformation,
                    )
                )
                return
        self.cover_preview.setPixmap(QPixmap())
        self.cover_preview.setText("暂无封面")

    def _choose_cover(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "选择封面图片", "", "图片文件 (*.png *.jpg *.jpeg)"
        )
        if not path:
            return

        if self.is_new:
            self._pending_cover_path = path
            self._load_cover_preview()
        else:
            if bm.set_cover(self.book_dir, path):
                self._load_cover_preview()
            else:
                QMessageBox.warning(self, "失败", "封面设置失败。")

    def _remove_cover(self):
        if self.is_new:
            self._pending_cover_path = None
            self._load_cover_preview()
            return

        reply = QMessageBox.question(self, "确认", "确定要移除封面吗？")
        if reply != QMessageBox.Yes:
            return
        bm.remove_cover(self.book_dir)
        self._load_cover_preview()

    # ============================================================
    # 保存
    # ============================================================
    def _save(self):
        title = self.title_edit.text().strip()
        if not title:
            self.title_field.set_error("书名不能为空")
            self.title_edit.setFocus()
            return

        author = self.author_edit.text().strip()
        description = self.desc_edit.toPlainText()

        if self.is_new:
            book_dir, project_path = bm.create_book(title)
            self.book_dir = book_dir
            self.is_new = False

            meta = bm.load_meta(book_dir)
            meta["title"] = title
            meta["author"] = author
            meta["description"] = description
            bm.save_meta(book_dir, meta)

            if self._pending_cover_path:
                if not bm.set_cover(book_dir, self._pending_cover_path):
                    QMessageBox.warning(
                        self, "提示",
                        "封面复制失败，书籍已创建但不含封面。"
                    )
                self._pending_cover_path = None

            if os.path.exists(project_path):
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["title"] = title
                    with open(project_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass
        else:
            self.meta["title"] = title
            self.meta["author"] = author
            self.meta["description"] = description
            bm.save_meta(self.book_dir, self.meta)

            project_path = bm.get_project_path(self.book_dir)
            if os.path.exists(project_path):
                try:
                    with open(project_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    data["title"] = title
                    with open(project_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False, indent=2)
                except Exception:
                    pass

        self.accept()

    def get_book_dir(self):
        """返回书籍目录（新建模式下，保存成功后才有效）"""
        return self.book_dir
