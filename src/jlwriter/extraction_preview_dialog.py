"""
档案提取预览对话框：分 Tab 展示各类型实体的新增与补充
"""
from .ui.literary import LiteraryDialog
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QWidget, QTreeWidget, QTreeWidgetItem, QMessageBox
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QBrush, QFont

from .extraction_preview import apply_selected, summarize_diff


class ExtractionPreviewDialog(LiteraryDialog):
    """
    差异预览：
    - 每个类型一个 Tab
    - 树形展示：新增 / 补充 两个分组
    - 每个节点可勾选，默认全选
    - 确认后调用 apply_selected
    """

    def __init__(self, project, extracted, diff, parent=None):
        super().__init__(parent)
        self.project = project
        self.extracted = extracted
        self.diff = diff
        self._applied = False
        self._stats = None

        self.setWindowTitle("档案提取预览")
        self.resize(1000, 800)

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel(
            "AI 已从选中章节提取到以下实体。请选择要应用的项目，"
            "未勾选的内容将被忽略。"
        ))

        self.tabs = QTabWidget()
        self._type_widgets = {}

        for key, label in [
            ("characters", "角色"),
            ("monsters", "怪物"),  # 新增
            ("relations", "关系"),
            ("locations", "地点"),
            ("organizations", "组织"),
            ("items", "物品"),
        ]:
            tab = self._build_type_tab(key, label)
            self.tabs.addTab(tab, label)
        layout.addWidget(self.tabs, 1)

        # 全选/全不选
        sel_row = QHBoxLayout()
        all_btn = QPushButton("全选")
        all_btn.clicked.connect(lambda: self._toggle_all(True))
        none_btn = QPushButton("全不选")
        none_btn.clicked.connect(lambda: self._toggle_all(False))
        sel_row.addWidget(all_btn)
        sel_row.addWidget(none_btn)
        sel_row.addStretch()

        self.summary_label = QLabel(summarize_diff(diff))
        self.summary_label.setProperty("role", "hint")
        sel_row.addWidget(self.summary_label)
        layout.addLayout(sel_row)

        # 底部按钮
        bottom = QHBoxLayout()
        bottom.addStretch()

        self.apply_btn = QPushButton("应用选中项")
        self.apply_btn.clicked.connect(self._apply)
        bottom.addWidget(self.apply_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

    # ============================================================
    # Tab 构建
    # ============================================================
    def _build_type_tab(self, key, label):
        tab = QWidget()
        v = QVBoxLayout(tab)

        tree = QTreeWidget()
        tree.setHeaderLabels(["选择", "内容"])
        tree.setColumnWidth(0, 60)
        tree.setIndentation(18)
        v.addWidget(tree)

        d = self.diff.get(key, {})
        new_list = d.get("new") or []
        supplement_list = d.get("supplement") or []

        # 新增分组
        if new_list:
            new_root = QTreeWidgetItem(tree, [f"新增（{len(new_list)}）", ""])
            new_root.setExpanded(True)
            font = QFont()
            font.setBold(True)
            new_root.setFont(0, font)
            new_root.setForeground(0, QBrush(QColor("#4CAF50")))

            for item in new_list:
                child = QTreeWidgetItem(new_root, ["", self._describe_new(key, item)])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked)
                child.setData(0, Qt.UserRole, ("new", item))

        # 补充分组
        if supplement_list:
            sup_root = QTreeWidgetItem(tree, [f"补充（{len(supplement_list)}）", ""])
            sup_root.setExpanded(True)
            font = QFont()
            font.setBold(True)
            sup_root.setFont(0, font)
            sup_root.setForeground(0, QBrush(QColor("#FF9800")))

            for item in supplement_list:
                child = QTreeWidgetItem(sup_root, ["", self._describe_supplement(key, item)])
                child.setFlags(child.flags() | Qt.ItemIsUserCheckable)
                child.setCheckState(0, Qt.Checked)
                child.setData(0, Qt.UserRole, ("supplement", item))

        if not new_list and not supplement_list:
            empty = QTreeWidgetItem(tree, ["", "（无）"])
            empty.setForeground(1, QBrush(QColor("#AAA")))

        self._type_widgets[key] = tree
        return tab

    def _describe_new(self, key, item):
        """新增实体的一行描述"""
        if key == "characters":
            name = item.get("name", "")
            desc = (item.get("personality") or item.get("appearance") or "")
            desc = desc[:60]
            return f"【角色】{name}" + (f"｜{desc}" if desc else "")
        if key == "relations":
            return (
                f"【关系】{item.get('from', '')} → {item.get('to', '')}"
                f"（{item.get('type', '')}）{item.get('description', '')[:40]}"
            )
        if key == "monsters":
            name = item.get("name", "")
            cat = item.get("category", "")
            desc = (item.get("behavior_ability") or item.get("appearance") or "")[:60]
            return (
                f"【怪物】{name}"
                + (f"（{cat}）" if cat else "")
                + (f"｜{desc}" if desc else "")
            )
        if key == "locations":
            name = item.get("name", "")
            lvl = item.get("level", "")
            desc = (item.get("description") or "")[:60]
            return f"【地点】{name}（{lvl}）" + (f"｜{desc}" if desc else "")
        if key == "organizations":
            name = item.get("name", "")
            nature = item.get("nature", "")
            desc = (item.get("description") or "")[:60]
            return f"【组织】{name}（{nature}）" + (f"｜{desc}" if desc else "")
        if key == "items":
            name = item.get("name", "")
            typ = item.get("type", "")
            desc = (item.get("ability") or item.get("description") or "")[:60]
            return f"【物品】{name}（{typ}）" + (f"｜{desc}" if desc else "")
        return str(item)[:100]

    def _describe_supplement(self, key, item):
        """补充项的一行描述"""
        name = item.get("name", "")
        fields = item.get("fields") or []
        field_parts = []
        for f in fields:
            label = f.get("label", f.get("field", ""))
            v = f.get("value")
            if f.get("is_list"):
                v_text = f"[{len(v)} 项]"
            else:
                v_text = str(v)[:40]
            field_parts.append(f"{label}={v_text}")
        return f"【补充】{name} ｜ " + "；".join(field_parts)

    # ============================================================
    # 操作
    # ============================================================
    def _toggle_all(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for tree in self._type_widgets.values():
            for i in range(tree.topLevelItemCount()):
                root = tree.topLevelItem(i)
                for j in range(root.childCount()):
                    root.child(j).setCheckState(0, state)

    def _collect_selected(self):
        selected = {
            "characters_new": set(),
            "characters_supplement": set(),
            "relations_new": set(),
            "monsters_new": set(),
            "monsters_supplement": set(),
            "locations_new": set(),
            "locations_supplement": set(),
            "organizations_new": set(),
            "organizations_supplement": set(),
            "items_new": set(),
            "items_supplement": set(),
        }
        for key, tree in self._type_widgets.items():
            for i in range(tree.topLevelItemCount()):
                root = tree.topLevelItem(i)
                for j in range(root.childCount()):
                    child = root.child(j)
                    if child.checkState(0) != Qt.Checked:
                        continue
                    data = child.data(0, Qt.UserRole)
                    if not data:
                        continue
                    kind, item = data

                    if key == "relations":
                        if kind == "new":
                            sel_key = "relations_new"
                            selected[sel_key].add((
                                (item.get("from") or "").strip(),
                                (item.get("to") or "").strip(),
                                (item.get("type") or "").strip() or "关系",
                            ))
                    else:
                        name = (item.get("name") or "").strip()
                        if name:
                            selected[f"{key}_{kind}"].add(name)
        return selected

    def _apply(self):
        selected = self._collect_selected()

        total = sum(len(v) for v in selected.values())
        if total == 0:
            QMessageBox.information(self, "提示", "未勾选任何项目。")
            return

        try:
            stats = apply_selected(self.project, self.extracted, selected)
        except Exception as e:
            QMessageBox.critical(self, "应用失败", str(e))
            return

        self._applied = True
        self._stats = stats

        parts = []
        for k, label in [
            ("characters", "角色"), ("relations", "关系"), ("monsters", "怪物"),   # 新增
            ("locations", "地点"), ("organizations", "组织"),
            ("items", "物品"),
        ]:
            n = stats.get(k, 0)
            if n:
                parts.append(f"{label} +{n}")
        msg = "；".join(parts) if parts else "未产生变化"

        QMessageBox.information(self, "已应用", f"档案已更新：{msg}")
        self.accept()

    # ============================================================
    # 查询
    # ============================================================
    def was_applied(self):
        return self._applied

    def get_stats(self):
        return self._stats