"""
导出对话框：范围选择 + 格式选择 + 路径选择
"""
from .ui.literary import LiteraryDialog
import os
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QRadioButton, QButtonGroup, QComboBox, QGroupBox, QMessageBox, QLineEdit, QFileDialog

from .chapter_select_dialog import ChapterSelectDialog
from .exporter import export_chapters, export_story_info


class ExportDialog(LiteraryDialog):
    def __init__(self, project, parent=None,
                 default_vol_idx=0, default_ch_idx=0):
        super().__init__(parent)
        self.project = project
        self._multi_chapters = None      # [(vi, ci), ...]

        self.setWindowTitle("导出")
        self.resize(760, 800)

        layout = QVBoxLayout(self)

        # ---------- 范围选择 ----------
        range_group = QGroupBox("导出范围")
        range_layout = QVBoxLayout(range_group)

        self.range_btn_group = QButtonGroup(self)

        self.rb_book = QRadioButton("整本书")
        self.rb_volume = QRadioButton("单卷")
        self.rb_chapter = QRadioButton("单章")
        self.rb_multi = QRadioButton("多章")
        self.rb_story = QRadioButton("故事设定")

        # 改用 toggled：签名为 (checked: bool)，无重载歧义
        for rb in (self.rb_book, self.rb_volume, self.rb_chapter,
                   self.rb_multi, self.rb_story):
            self.range_btn_group.addButton(rb)
            rb.toggled.connect(self._on_range_changed)

        range_layout.addWidget(self.rb_book)

        vol_row = QHBoxLayout()
        vol_row.addWidget(self.rb_volume)
        self.volume_combo = QComboBox()
        for vi, vol in enumerate(project.volumes):
            self.volume_combo.addItem(
                f"第{vi + 1}卷 {vol.title}", vi
            )
        vol_row.addWidget(self.volume_combo, 1)
        range_layout.addLayout(vol_row)

        ch_row = QHBoxLayout()
        ch_row.addWidget(self.rb_chapter)
        self.chapter_combo = QComboBox()
        ch_row.addWidget(self.chapter_combo, 1)
        range_layout.addLayout(ch_row)

        multi_row = QHBoxLayout()
        multi_row.addWidget(self.rb_multi)
        self.multi_btn = QPushButton("选择章节...")
        self.multi_btn.clicked.connect(self._open_multi_selector)
        self.multi_label = QLabel("未选择")
        self.multi_label.setProperty("role", "hint")
        multi_row.addWidget(self.multi_btn)
        multi_row.addWidget(self.multi_label, 1)
        range_layout.addLayout(multi_row)

        range_layout.addWidget(self.rb_story)
        layout.addWidget(range_group)

        # ---------- 格式选择 ----------
        fmt_group = QGroupBox("导出格式")
        fmt_layout = QVBoxLayout(fmt_group)

        self.fmt_btn_group = QButtonGroup(self)
        self.rb_txt = QRadioButton("TXT（纯文本）")
        self.rb_md = QRadioButton("Markdown（.md）")
        self.rb_pdf = QRadioButton("PDF（分页文档）")
        self.rb_png = QRadioButton("长图（PNG，仅单章）")

        for rb in (self.rb_txt, self.rb_md, self.rb_pdf, self.rb_png):
            fmt_layout.addWidget(rb)
            self.fmt_btn_group.addButton(rb)

        self.rb_md.setChecked(True)
        layout.addWidget(fmt_group)

        # ---------- 输出路径 ----------
        path_group = QGroupBox("输出位置")
        path_layout = QVBoxLayout(path_group)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("尚未选择...")
        path_row.addWidget(self.path_edit, 1)
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self._browse_path)
        path_row.addWidget(self.browse_btn)
        path_layout.addLayout(path_row)

        layout.addWidget(path_group)

        layout.addStretch()

        # ---------- 底部按钮 ----------
        bottom = QHBoxLayout()
        bottom.addStretch()
        export_btn = QPushButton("导出")
        export_btn.clicked.connect(self._do_export)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(export_btn)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

        # ---------- 初始化 ----------
        self.volume_combo.currentIndexChanged.connect(
            self._refresh_chapter_combo
        )
        if default_vol_idx < len(project.volumes):
            self.volume_combo.setCurrentIndex(default_vol_idx)
        self._refresh_chapter_combo()

        # 触发一次同步（setChecked 会触发 toggled → _on_range_changed）
        self.rb_book.setChecked(True)

    # ============================================================
    # 联动
    # ============================================================
    def _on_range_changed(self, checked=False):
        # toggled 会同时触发"取消选中"和"选中"两次，
        # 只对"选中"这一侧做出反应
        if not checked:
            return

        # 卷、章下拉仅在其对应范围下可用
        self.volume_combo.setEnabled(self.rb_volume.isChecked())
        self.chapter_combo.setEnabled(self.rb_chapter.isChecked())
        self.multi_btn.setEnabled(self.rb_multi.isChecked())

        # 长图仅对单章可用
        if self.rb_png.isChecked() and not self.rb_chapter.isChecked():
            self.rb_md.setChecked(True)
        self.rb_png.setEnabled(self.rb_chapter.isChecked())

        self._refresh_default_path()

    def _refresh_chapter_combo(self):
        vi = self.volume_combo.currentData()
        self.chapter_combo.clear()
        if vi is None:
            return
        vol = self.project.volumes[vi]
        for ci, ch in enumerate(vol.chapters):
            self.chapter_combo.addItem(
                f"第{ci + 1}章 {ch.title}", ci
            )

    def _open_multi_selector(self):
        dlg = ChapterSelectDialog(
            self.project, self, title="选择要导出的章节"
        )
        if dlg.exec_() != QDialog.Accepted:
            return
        selected = dlg.get_selected_chapters()
        if not selected:
            self._multi_chapters = None
            self.multi_label.setText("未选择")
            return
        self._multi_chapters = selected
        self.multi_label.setText(f"已选 {len(selected)} 章")

    # ============================================================
    # 输出路径
    # ============================================================
    def _suggest_filename(self):
        title = self.project.title or "作品"
        if self.rb_story.isChecked():
            base = f"{title} - 故事设定"
        elif self.rb_book.isChecked():
            base = title
        elif self.rb_volume.isChecked():
            vi = self.volume_combo.currentData()
            vol = self.project.volumes[vi]
            base = f"{title} - {vol.title}"
        elif self.rb_chapter.isChecked():
            vi = self.volume_combo.currentData()
            ci = self.chapter_combo.currentData()
            if vi is None or ci is None:
                base = f"{title} - 章节"
            else:
                vol = self.project.volumes[vi]
                ch = vol.chapters[ci]
                base = f"{title} - {vol.title} - {ch.title}"
        elif self.rb_multi.isChecked():
            base = f"{title} - 选中章节"
        else:
            base = title

        ext = self._current_ext()
        return self._sanitize(base) + ext

    def _current_ext(self):
        if self.rb_txt.isChecked():
            return ".txt"
        if self.rb_md.isChecked():
            return ".md"
        if self.rb_pdf.isChecked():
            return ".pdf"
        if self.rb_png.isChecked():
            return ".png"
        return ".txt"

    def _sanitize(self, name):
        for ch in '\\/:*?"<>|':
            name = name.replace(ch, "_")
        return name

    def _refresh_default_path(self):
        # 每次范围/格式变化时，尝试刷新默认文件名（若用户已手动改动路径则保留）
        if not self.path_edit.text():
            default_dir = os.path.expanduser("~")
            self.path_edit.setText(
                os.path.join(default_dir, self._suggest_filename())
            )
        else:
            # 保留目录，替换文件名
            current_dir = os.path.dirname(self.path_edit.text())
            self.path_edit.setText(
                os.path.join(current_dir, self._suggest_filename())
            )

    def _browse_path(self):
        fmt = self._current_ext().lstrip(".")
        filters = {
            "txt": "文本文件 (*.txt)",
            "md": "Markdown 文件 (*.md)",
            "pdf": "PDF 文件 (*.pdf)",
            "png": "PNG 图片 (*.png)",
        }
        path, _ = QFileDialog.getSaveFileName(
            self, "选择导出位置",
            self.path_edit.text() or self._suggest_filename(),
            filters.get(fmt, "所有文件 (*)"),
        )
        if path:
            self.path_edit.setText(path)

    # ============================================================
    # 导出
    # ============================================================
    def _do_export(self):
        path = self.path_edit.text().strip()
        if not path:
            QMessageBox.warning(self, "提示", "请先选择输出位置。")
            return

        # 范围解析
        if self.rb_story.isChecked():
            fmt = self._current_ext().lstrip(".")
            try:
                export_story_info(self.project, fmt, path)
            except Exception as e:
                QMessageBox.critical(self, "导出失败", str(e))
                return
            QMessageBox.information(self, "完成", f"已导出到：\n{path}")
            self.accept()
            return

        chapters = self._resolve_chapters()
        if chapters is not None and len(chapters) == 0:
            QMessageBox.information(self, "提示", "未选择任何章节。")
            return

        fmt = self._current_ext().lstrip(".")

        if fmt == "png":
            if chapters is None or len(chapters) != 1:
                QMessageBox.warning(
                    self, "提示", "长图仅支持导出单章。"
                )
                return

        try:
            export_chapters(self.project, chapters, fmt, path)
        except Exception as e:
            QMessageBox.critical(self, "导出失败", str(e))
            return

        QMessageBox.information(self, "完成", f"已导出到：\n{path}")
        self.accept()

    def _resolve_chapters(self):
        if self.rb_book.isChecked():
            return None
        if self.rb_volume.isChecked():
            vi = self.volume_combo.currentData()
            if vi is None:
                return []
            vol = self.project.volumes[vi]
            return [(vi, ci) for ci in range(len(vol.chapters))]
        if self.rb_chapter.isChecked():
            vi = self.volume_combo.currentData()
            ci = self.chapter_combo.currentData()
            if vi is None or ci is None:
                return []
            return [(vi, ci)]
        if self.rb_multi.isChecked():
            return self._multi_chapters or []
        return None