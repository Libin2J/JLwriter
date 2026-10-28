from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QTextEdit, QMessageBox, QCheckBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QFont
from PyQt5.QtWidgets import QSizePolicy   # 顶部补充导入
from .ui.base_dialog import BaseDialog
from .ui.tokens import SPACING
from .ui.widgets.section import EmptyState


SEVERITY_COLORS = {
    "high": "#F44336",
    "medium": "#FF9800",
    "low": "#9E9E9E",
}
SEVERITY_LABELS = {"high": "高", "medium": "中", "low": "低"}


class ReviewReportDialog(BaseDialog):
    def __init__(self, report: dict, parent=None):
        self.report = report
        self._request_revision = False
        self._issue_checks = []

        super().__init__(
            parent,
            title="AI 审核报告",
            subtitle="勾选需要让 AI 生成修订方案的问题",
            default_size=(1500, 1000),
            min_size=(820, 620),
            show_button_bar=False,
        )

    def build_content(self, layout):
        # ---- 分数 ----
        score = self.report.get("overall_score", 0)
        color = (
            "#4CAF50" if score >= 75 else
            "#FF9800" if score >= 60 else "#F44336"
        )
        score_label = QLabel(f"综合评分：{score} / 100")
        score_label.setStyleSheet(
            f"font-size: 16px; font-weight: bold; color: {color};"
        )
        layout.addWidget(score_label)

        if self.report.get("thought"):
            t = QLabel(f"<i>{self.report['thought']}</i>")
            t.setProperty("role", "hint")
            t.setWordWrap(True)
            layout.addWidget(t)

        issues = self.report.get("issues", [])

        # ---- 无问题时显示空状态 ----
        if not issues:
            layout.addWidget(
                EmptyState("√", "审核未发现问题", "本阶段内容通过审核")
            )
            return

        # ---- 问题表格 ----
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(
            ["选择", "严重度", "方面", "问题", "建议"]
        )
        self.table.setWordWrap(True)

        # 关键修正：水平 Expanding（按布局分配），垂直 Expanding + 最小高度
        self.table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.table.setMinimumHeight(220)

        header = self.table.horizontalHeader()

        # 关键修正：不使用 setStretchLastSection（会与 Stretch 模式冲突）
        header.setStretchLastSection(False)

        # 列宽策略
        header.setSectionResizeMode(0, QHeaderView.Fixed)
        self.table.setColumnWidth(0, 44)

        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 60)

        header.setSectionResizeMode(2, QHeaderView.Interactive)
        self.table.setColumnWidth(2, 120)

        header.setSectionResizeMode(3, QHeaderView.Stretch)
        header.setSectionResizeMode(4, QHeaderView.Stretch)

        # 行高随内容自适应
        self.table.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeToContents
        )

        self.table.setRowCount(len(issues))

        for row, it in enumerate(issues):
            chk = QCheckBox()
            chk.setChecked(it.get("severity") in ("high", "medium"))
            self.table.setCellWidget(row, 0, chk)
            self._issue_checks.append(chk)

            sev = it.get("severity", "low")
            item_sev = QTableWidgetItem(
                {"high": "高", "medium": "中", "low": "低"}.get(sev, sev)
            )
            item_sev.setForeground(QBrush(QColor(
                {"high": "#F44336", "medium": "#FF9800",
                 "low": "#9E9E9E"}.get(sev, "#9E9E9E")
            )))
            f = QFont()
            f.setBold(True)
            item_sev.setFont(f)
            item_sev.setFlags(item_sev.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 1, item_sev)

            aspect = it.get("aspect", "")
            if it.get("arc_index") is not None:
                aspect += f"（弧{it['arc_index']}）"
            if it.get("chapter_index") is not None:
                aspect += f"（第{it['chapter_index']}章）"
            item_aspect = QTableWidgetItem(aspect)
            item_aspect.setFlags(item_aspect.flags() & ~Qt.ItemIsEditable)
            self.table.setItem(row, 2, item_aspect)

            for col, text in [(3, it.get("description", "")),
                              (4, it.get("suggestion", ""))]:
                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.table.setItem(row, col, item)

        layout.addWidget(self.table, 1)

        # ---- 全选 / 全不选 ----
        sel_row = QHBoxLayout()
        sel_row.setSpacing(SPACING.sm)
        select_all_btn = QPushButton("全选")
        select_all_btn.setProperty("role", "ghost")
        select_all_btn.clicked.connect(lambda: self._set_all(True))
        deselect_btn = QPushButton("全不选")
        deselect_btn.setProperty("role", "ghost")
        deselect_btn.clicked.connect(lambda: self._set_all(False))
        sel_row.addWidget(select_all_btn)
        sel_row.addWidget(deselect_btn)
        sel_row.addStretch()
        layout.addLayout(sel_row)

        # ---- 亮点 ----
        if self.report.get("highlights"):
            layout.addWidget(QLabel("做得好的地方："))
            hl = QTextEdit()
            hl.setReadOnly(True)
            hl.setMaximumHeight(70)
            hl.setPlainText(
                "\n".join(f"· {h}" for h in self.report["highlights"])
            )
            layout.addWidget(hl)

    def build_footer(self, root_layout):
        bar = QHBoxLayout()
        bar.setSpacing(SPACING.sm)
        bar.setContentsMargins(0, SPACING.sm, 0, 0)
        bar.addStretch()

        if self.report.get("issues"):
            rev_btn = QPushButton("为勾选的问题生成修订方案")
            rev_btn.setProperty("role", "primary")
            rev_btn.clicked.connect(self._on_request_revision)
            bar.addWidget(rev_btn)

        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bar.addWidget(close_btn)

        root_layout.addLayout(bar)

    def _set_all(self, checked):
        for c in self._issue_checks:
            c.setChecked(checked)

    def _on_request_revision(self):
        selected = [
            it for it, chk in zip(self.report["issues"], self._issue_checks)
            if chk.isChecked()
        ]
        if not selected:
            QMessageBox.information(self, "提示", "请至少勾选一个问题。")
            return
        self.report["selected_issues"] = selected
        self._request_revision = True
        self.accept()

    def request_revision(self) -> bool:
        return self._request_revision

    def get_selected_issues(self):
        return self.report.get("selected_issues", [])