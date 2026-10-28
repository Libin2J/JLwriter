"""
规划差异对比对话框：偏离报告 + 实体关系校验 + LLM 修正
"""
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QPlainTextEdit,
    QMessageBox, QProgressBar, QSplitter, QWidget, QTabWidget
)
from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QBrush, QFont

from .ai_assistant import AIRequestThread
from .plan_comparator import build_deviation_prompt, parse_deviation_response, build_relation_check_prompt, parse_relation_check_response, build_correction_prompt, DIMENSION_LABELS, STATUS_LABELS, STATUS_COLORS


class PlanDeviationDialog(BaseDialog):
    def __init__(self, project, vol_idx, ch_idx, ai_config, parent=None):
        self.project = project
        self.vol_idx = vol_idx
        self.ch_idx = ch_idx
        self.ai_config = ai_config
        self._applied = False
        self._report_thread = None
        self._relation_thread = None
        self._fix_thread = None
        self._report = None
        self._relation_issues = []
        self._closing = False

        vol = project.volumes[vol_idx]
        ch = vol.chapters[ch_idx]
        self.chapter = ch

        super().__init__(
            parent,
            title=f"规划差异对比",
            subtitle=f"第{vol_idx + 1}卷《{vol.title}》· 第{ch_idx + 1}章《{ch.title}》",
            default_size=(1500, 1000),
            min_size=(820, 600),
            show_button_bar=False,
        )

        # 延迟启动，避免 UI 未就绪
        QTimer.singleShot(80, self._start_analysis)

    def build_content(self, layout):
        # 顶部：分数
        self.score_label = QLabel("尚未分析")
        self.score_label.setProperty("role", "subtitle")
        layout.addWidget(self.score_label)

        # Tab
        self.tabs = QTabWidget()
        tab1 = QWidget()
        t1 = QVBoxLayout(tab1)
        t1.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)

        self.deviation_table = QTableWidget()
        self.deviation_table.setColumnCount(5)
        self.deviation_table.setHorizontalHeaderLabels(
            ["维度", "状态", "规划", "实际", "说明"]
        )
        h = self.deviation_table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.Stretch)
        h.setSectionResizeMode(4, QHeaderView.Stretch)
        self.deviation_table.setWordWrap(True)
        self.deviation_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        t1.addWidget(self.deviation_table)

        t1.addWidget(QLabel("规划外多出的内容："))
        self.extra_edit = QPlainTextEdit()
        self.extra_edit.setReadOnly(True)
        self.extra_edit.setMaximumHeight(90)
        t1.addWidget(self.extra_edit)

        t1.addWidget(QLabel("总结与建议："))
        self.summary_edit = QPlainTextEdit()
        self.summary_edit.setReadOnly(True)
        self.summary_edit.setMaximumHeight(100)
        t1.addWidget(self.summary_edit)

        self.tabs.addTab(tab1, "维度偏离")

        tab2 = QWidget()
        t2 = QVBoxLayout(tab2)
        t2.setContentsMargins(SPACING.md, SPACING.md, SPACING.md, SPACING.md)

        self.relation_table = QTableWidget()
        self.relation_table.setColumnCount(4)
        self.relation_table.setHorizontalHeaderLabels(
            ["严重度", "关系", "问题", "建议"]
        )
        h2 = self.relation_table.horizontalHeader()
        h2.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h2.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h2.setSectionResizeMode(2, QHeaderView.Stretch)
        h2.setSectionResizeMode(3, QHeaderView.Stretch)
        self.relation_table.setWordWrap(True)
        self.relation_table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )
        t2.addWidget(self.relation_table)

        t2.addWidget(QLabel("关系校验说明："))
        self.relation_summary = QPlainTextEdit()
        self.relation_summary.setReadOnly(True)
        self.relation_summary.setMaximumHeight(120)
        t2.addWidget(self.relation_summary)

        self.tabs.addTab(tab2, "关系校验")
        self.tabs.currentChanged.connect(self._on_tab_changed)

        layout.addWidget(self.tabs, 1)

        # 进度
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        layout.addWidget(self.progress)

        self.status_label = QLabel("准备中...")
        self.status_label.setProperty("role", "hint")
        layout.addWidget(self.status_label)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)
        bar.addStretch()

        self.reanalyze_btn = QPushButton("重新分析")
        self.reanalyze_btn.clicked.connect(self._start_analysis)
        bar.addWidget(self.reanalyze_btn)

        self.fix_btn = QPushButton("让 AI 修正本章正文")
        self.fix_btn.setProperty("role", "primary")
        self.fix_btn.clicked.connect(self._start_fix)
        self.fix_btn.setEnabled(False)
        bar.addWidget(self.fix_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bar.addWidget(close_btn)

        root_layout.addLayout(bar)

    # ============================================================
    # 分析
    # ============================================================
    def _start_analysis(self):
        if self._closing:
            return
        if self._is_busy():
            QMessageBox.information(self, "提示", "正在分析中...")
            return

        ch = self.chapter
        if not ch.plan:
            QMessageBox.information(self, "提示", "该章节尚无规划，无法对比。")
            self.reject()
            return
        if not (ch.content or "").strip():
            QMessageBox.information(self, "提示", "该章节正文为空，无法对比。")
            self.reject()
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(
                self, "提示",
                "审核 Agent 未配置 API Key，请到 AI 设置中填写。"
            )
            self.reject()
            return

        self.progress.show()
        self.status_label.setText("正在分析规划偏离与关系校验...")
        self.score_label.setText("分析中...")
        self.score_label.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #888;"
        )
        self.reanalyze_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self._clear_display()

        # 启动偏离分析
        self._start_deviation_check(resolved)

    def _start_deviation_check(self, resolved):
        prompt = build_deviation_prompt(
            self.project, self.vol_idx, self.ch_idx, self.chapter
        )
        self._report_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*6, json_mode=True, timeout=120,
        )
        self._report_thread.finished.connect(self._on_deviation_finished)
        self._report_thread.error.connect(self._on_deviation_error)
        self._report_thread.finished.connect(self._report_thread.deleteLater)
        self._report_thread.start()

    def _on_deviation_finished(self, text):
        self._report_thread = None
        if self._closing:
            return
        try:
            report = parse_deviation_response(text, self.chapter.title)
            self._report = report
            self._render_report(report)
        except Exception as e:
            self.status_label.setText(f"偏离解析失败：{e}")
            self._finish_analysis(False)
            return

        # 继续关系校验
        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            self._finish_analysis(True)
            return
        self._start_relation_check(resolved)

    def _on_deviation_error(self, err):
        self._report_thread = None
        if self._closing:
            return
        self.status_label.setText(f"偏离分析失败：{err}")
        self._finish_analysis(False)

    def _start_relation_check(self, resolved):
        self.status_label.setText("正在校验实体关系...")
        prompt = build_relation_check_prompt(
            self.project, self.vol_idx, self.ch_idx, self.chapter
        )
        self._relation_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*6, json_mode=True, timeout=120,
        )
        self._relation_thread.finished.connect(self._on_relation_finished)
        self._relation_thread.error.connect(self._on_relation_error)
        self._relation_thread.finished.connect(
            self._relation_thread.deleteLater
        )
        self._relation_thread.start()

    def _on_relation_finished(self, text):
        self._relation_thread = None
        if self._closing:
            return
        try:
            issues, summary = parse_relation_check_response(text)
            self._relation_issues = issues
            self._render_relation_issues(issues, summary)
        except Exception as e:
            self.status_label.setText(f"关系校验解析失败：{e}")
            self._finish_analysis(True)
            return
        self._finish_analysis(True)

    def _on_relation_error(self, err):
        self._relation_thread = None
        if self._closing:
            return
        self.status_label.setText(f"关系校验失败：{err}")
        self._finish_analysis(True)

    def _finish_analysis(self, success):
        self.progress.hide()
        self.reanalyze_btn.setEnabled(True)
        if self._report:
            score = self._report.overall_score
            color = (
                "#4CAF50" if score >= 75 else
                "#FF9800" if score >= 60 else "#F44336"
            )
            self.score_label.setText(
                f"{score} 分 · {self._report.level}"
            )
            self.score_label.setStyleSheet(
                f"font-size: 16px; font-weight: bold; color: {color};"
            )
            self.status_label.setText("分析完成")
            self.fix_btn.setEnabled(True)
        else:
            self.score_label.setText("分析失败")
            self.score_label.setStyleSheet(
                "font-size: 16px; font-weight: bold; color: #F44336;"
            )

    def _is_busy(self):
        return any([
            self._report_thread and self._report_thread.isRunning(),
            self._relation_thread and self._relation_thread.isRunning(),
            self._fix_thread and self._fix_thread.isRunning(),
        ])

    # ============================================================
    # 渲染
    # ============================================================
    def _clear_display(self):
        self.deviation_table.setRowCount(0)
        self.extra_edit.clear()
        self.summary_edit.clear()
        self.relation_table.setRowCount(0)
        self.relation_summary.clear()

    def _render_report(self, report):
        self.deviation_table.setRowCount(len(report.dimensions))
        for row, d in enumerate(report.dimensions):
            dim_label = DIMENSION_LABELS.get(d.dimension, d.dimension)
            status_label = STATUS_LABELS.get(d.status, d.status)
            status_color = STATUS_COLORS.get(d.status, "#9E9E9E")

            item_dim = QTableWidgetItem(dim_label)
            item_dim.setFlags(item_dim.flags() & ~Qt.ItemIsEditable)
            self.deviation_table.setItem(row, 0, item_dim)

            item_status = QTableWidgetItem(status_label)
            item_status.setFlags(item_status.flags() & ~Qt.ItemIsEditable)
            item_status.setForeground(QBrush(QColor(status_color)))
            f = QFont()
            f.setBold(True)
            item_status.setFont(f)
            self.deviation_table.setItem(row, 1, item_status)

            for col, text in [(2, d.planned), (3, d.actual), (4, d.comment)]:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.deviation_table.setItem(row, col, item)

        if report.extra_content:
            self.extra_edit.setPlainText(
                "\n".join(f"· {e}" for e in report.extra_content)
            )
        else:
            self.extra_edit.setPlainText("（无）")

        parts = []
        if report.summary:
            parts.append(f"总结：{report.summary}")
        if report.suggestions:
            parts.append(f"建议：{report.suggestions}")
        self.summary_edit.setPlainText(
            "\n\n".join(parts) if parts else "（无）"
        )

    def _render_relation_issues(self, issues, summary):
        self.relation_table.setRowCount(len(issues))
        for row, it in enumerate(issues):
            sev = it.get("severity", "low")
            item_sev = QTableWidgetItem(
                {"high": "高", "medium": "中", "low": "低"}.get(sev, sev)
            )
            color = {"high": "#F44336", "medium": "#FF9800",
                     "low": "#9E9E9E"}.get(sev, "#9E9E9E")
            item_sev.setForeground(QBrush(QColor(color)))
            f = QFont()
            f.setBold(True)
            item_sev.setFont(f)
            item_sev.setFlags(item_sev.flags() & ~Qt.ItemIsEditable)
            self.relation_table.setItem(row, 0, item_sev)

            rel_text = (
                f"{it.get('from', '')} → {it.get('to', '')}"
                f"（{it.get('type', '')}）"
            )
            item_rel = QTableWidgetItem(rel_text)
            item_rel.setFlags(item_rel.flags() & ~Qt.ItemIsEditable)
            self.relation_table.setItem(row, 1, item_rel)

            for col, text in [(2, it.get("description", "")),
                              (3, it.get("suggestion", ""))]:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.relation_table.setItem(row, col, item)

        if not issues:
            self.relation_summary.setPlainText(
                "未发现关系时序问题。"
                + (f"\n\n{summary}" if summary else "")
            )
        else:
            self.relation_summary.setPlainText(
                f"共 {len(issues)} 条关系问题。\n"
                + (f"\n{summary}" if summary else "")
            )
        # 数据填充后延迟刷新一次，保证切到 Tab 2 时行高已正确
        QTimer.singleShot(0, self._refresh_relation_table_rows)

    def _on_tab_changed(self, index):
        """Tab 切换时刷新关系表行高，修复首次显示时的异常"""
        if index == 1:   # 关系校验 Tab
            QTimer.singleShot(0, self._refresh_relation_table_rows)

    def _refresh_relation_table_rows(self):
        """
        强制重算行高。
        根因：QTableWidget 在不可见的 QTabWidget 中填充数据时，
        ResizeToContents 依据的视口宽度尚未确定，导致行高异常；
        首次切换到可见后重新计算才能恢复正常。
        """
        try:
            self.relation_table.resizeRowsToContents()
        except Exception:
            pass

    # ============================================================
    # 修正
    # ============================================================
    def _start_fix(self):
        if self._closing:
            return
        if self._is_busy():
            QMessageBox.information(self, "提示", "正在处理中...")
            return
        if not self._report:
            return

        resolved = self.ai_config.resolve_agent("reviewer")
        if not resolved or not resolved.api_key:
            QMessageBox.warning(self, "提示", "审核 Agent 未配置 API Key。")
            return

        reply = QMessageBox.question(
            self, "确认修正",
            "AI 将基于偏离报告与关系校验结果修订本章正文。\n"
            "修订结果会先显示在预览框中，确认后才会覆盖原正文。\n"
            "是否继续？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes
        )
        if reply != QMessageBox.Yes:
            return

        self.progress.show()
        self.status_label.setText("AI 正在修正本章正文...")
        self.fix_btn.setEnabled(False)
        self.reanalyze_btn.setEnabled(False)

        prompt = build_correction_prompt(
            self.project, self.vol_idx, self.ch_idx,
            self.chapter, self._report, self._relation_issues
        )
        self._fix_thread = AIRequestThread(
            resolved, prompt, parent=self,
            max_tokens=8192*6, timeout=240,
        )
        self._fix_thread.finished.connect(self._on_fix_finished)
        self._fix_thread.error.connect(self._on_fix_error)
        self._fix_thread.finished.connect(self._fix_thread.deleteLater)
        self._fix_thread.start()

    def _on_fix_finished(self, text):
        self._fix_thread = None
        if self._closing:
            return
        self.progress.hide()
        self.status_label.setText("修正完成")
        self.reanalyze_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)

        preview = CorrectionPreviewDialog(
            self.chapter.content, text, parent=self
        )
        if preview.exec_() == BaseDialog.Accepted:
            new_content = preview.get_content()
            if new_content:
                self.chapter.content = new_content
                self._applied = True  # 新增
                QMessageBox.information(
                    self, "已应用",
                    "修正后的正文已写入本章。\n"
                    "如不满意，可使用撤销（Ctrl+Z）或从历史记录中恢复。"
                )
                self._stop_all_threads()
                self.accept()

    def _on_fix_error(self, err):
        self._fix_thread = None
        if self._closing:
            return
        self.progress.hide()
        self.reanalyze_btn.setEnabled(True)
        self.fix_btn.setEnabled(True)
        self.status_label.setText(f"修正失败：{err}")
        QMessageBox.warning(self, "修正失败", err)

    # ============================================================
    # 生命周期
    # ============================================================
    def _stop_all_threads(self):
        self._closing = True
        for attr in ("_report_thread", "_relation_thread", "_fix_thread"):
            thread = getattr(self, attr, None)
            if thread and thread.isRunning():
                try:
                    thread.stop()  # 请求中断
                    thread.quit()
                    if not thread.wait(3000):
                        # 3 秒仍不退，最后手段
                        thread.terminate()
                        thread.wait(500)
                except Exception:
                    pass

    def accept(self):
        self._stop_all_threads()
        super().accept()

    def reject(self):
        self._stop_all_threads()
        super().reject()

    def closeEvent(self, event):
        self._stop_all_threads()
        super().closeEvent(event)

    def get_report(self):
        return self._report

    def was_applied(self) -> bool:
        """返回本次对话是否成功应用了修正"""
        return self._applied


class CorrectionPreviewDialog(BaseDialog):
    def __init__(self, original, corrected, parent=None):
        self._corrected = corrected
        self._original = original
        super().__init__(
            parent,
            title="修正预览",
            subtitle="左侧为原正文，右侧为 AI 修正稿；可编辑右侧内容，确认后覆盖原正文",
            default_size=(1200, 820),
            min_size=(820, 540),
            show_button_bar=False,
        )
        self.showMaximized()

    def build_content(self, layout):
        splitter = QSplitter(Qt.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(QLabel("<b>原文</b>"))
        self.original_view = QPlainTextEdit()
        self.original_view.setReadOnly(True)
        self.original_view.setPlainText(self._original or "")
        left_layout.addWidget(self.original_view)
        splitter.addWidget(left)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.addWidget(QLabel("<b>修正稿（可编辑）</b>"))
        self.corrected_view = QPlainTextEdit()
        self.corrected_view.setPlainText(self._corrected or "")
        right_layout.addWidget(self.corrected_view)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.lg)
        bar.setContentsMargins(0, SPACING.lg, 0, 0)
        bar.addStretch()

        apply_btn = QPushButton("应用修正")
        apply_btn.setProperty("role", "primary")
        apply_btn.clicked.connect(self._on_apply)
        bar.addWidget(apply_btn)

        discard_btn = QPushButton("放弃")
        discard_btn.clicked.connect(self.reject)
        bar.addWidget(discard_btn)

        root_layout.addLayout(bar)

    def _on_apply(self):
        text = self.corrected_view.toPlainText().strip()
        if not text:
            QMessageBox.warning(self, "提示", "修正稿为空，无法应用。")
            return
        self._corrected = text
        self.accept()

    def get_content(self):
        return self._corrected