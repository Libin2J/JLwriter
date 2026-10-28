"""
关系网络 Tab：多实体类型关系编辑 + 图形可视化
"""
from .ui.literary import LiteraryDialog
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QSplitter, QDialog, QFormLayout,
    QComboBox, QPlainTextEdit, QMessageBox, QLineEdit,
)
from PyQt5.QtCore import Qt

from .models import ENTITY_TYPE_LABELS, format_endpoint, parse_endpoint, display_endpoint
from .relation_graph_view import RelationGraphScene, RelationGraphView


# 关系类型：按类别分组
RELATION_TYPES_GROUPS = [
    ("人物关系", [
        "师徒", "父子", "母子", "父女", "母女",
        "兄弟", "姐妹", "朋友", "恋人", "夫妻",
        "敌对", "仇敌", "盟友", "同门", "同僚",
        "上下级", "主仆", "其他",
    ]),
    ("组织归属", [
        "所属", "创建", "领导", "叛出", "依附",
    ]),
    ("地理归属", [
        "位于", "隶属于", "辖区", "通往",
    ]),
    ("物品归属", [
        "拥有", "使用", "炼制", "遗失", "封印",
    ]),
    ("战斗与驯服", [
        "敌对", "击杀", "封印", "驯服", "共生", "寄生",
    ]),
]


class RelationEditDialog(LiteraryDialog):
    """新增 / 编辑单条关系：来源与目标均可选实体类型"""

    def __init__(self, project, relation=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.relation = relation
        self._result = None

        self.setWindowTitle("编辑关系" if relation else "新增关系")
        self.resize(600, 450)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        # 来源
        self.from_type_combo = QComboBox()
        for k, v in ENTITY_TYPE_LABELS.items():
            self.from_type_combo.addItem(v, k)
        self.from_name_combo = QComboBox()
        self.from_name_combo.setEditable(True)
        self.from_name_combo.setMinimumWidth(200)

        from_row = QHBoxLayout()
        from_row.addWidget(self.from_type_combo)
        from_row.addWidget(self.from_name_combo, 1)
        form.addRow("来源:", from_row)

        # 目标
        self.to_type_combo = QComboBox()
        for k, v in ENTITY_TYPE_LABELS.items():
            self.to_type_combo.addItem(v, k)
        self.to_name_combo = QComboBox()
        self.to_name_combo.setEditable(True)
        self.to_name_combo.setMinimumWidth(200)

        to_row = QHBoxLayout()
        to_row.addWidget(self.to_type_combo)
        to_row.addWidget(self.to_name_combo, 1)
        form.addRow("目标:", to_row)

        # 关系类型（分组下拉）
        self.type_combo = QComboBox()
        self.type_combo.setEditable(True)
        self.type_combo.setMinimumWidth(220)
        for group_label, types in RELATION_TYPES_GROUPS:
            self.type_combo.addItem(f"━━ {group_label} ━━")
            # 分组标题项禁用选择
            idx = self.type_combo.count() - 1
            model = self.type_combo.model()
            item = model.item(idx)
            if item is not None:
                item.setEnabled(False)
            for t in types:
                self.type_combo.addItem(t)
        form.addRow("关系类型:", self.type_combo)

        self.desc_edit = QPlainTextEdit()
        self.desc_edit.setMaximumHeight(90)
        self.desc_edit.setPlaceholderText("可选，简要描述关系的背景或状态")
        form.addRow("说明:", self.desc_edit)

        layout.addLayout(form)

        # 类型切换 → 刷新名称列表
        self.from_type_combo.currentIndexChanged.connect(
            lambda _: self._refresh_name_list("from")
        )
        self.to_type_combo.currentIndexChanged.connect(
            lambda _: self._refresh_name_list("to")
        )

        # 初始化
        if relation:
            a_type, a_name = parse_endpoint(relation.get("from", ""))
            b_type, b_name = parse_endpoint(relation.get("to", ""))
            self._select_type(self.from_type_combo, a_type)
            self._select_type(self.to_type_combo, b_type)
            self._refresh_name_list("from")
            self._refresh_name_list("to")
            self.from_name_combo.setCurrentText(a_name)
            self.to_name_combo.setCurrentText(b_name)
            self.type_combo.setCurrentText(relation.get("type", ""))
            self.desc_edit.setPlainText(relation.get("description", ""))
        else:
            self._refresh_name_list("from")
            self._refresh_name_list("to")
            # 默认选前两个角色
            if self.from_name_combo.count() >= 2:
                self.from_name_combo.setCurrentIndex(0)
                self.to_name_combo.setCurrentIndex(1)

        bottom = QHBoxLayout()
        bottom.addStretch()
        ok_btn = QPushButton("确定")
        ok_btn.clicked.connect(self._on_ok)
        cancel_btn = QPushButton("取消")
        cancel_btn.clicked.connect(self.reject)
        bottom.addWidget(ok_btn)
        bottom.addWidget(cancel_btn)
        layout.addLayout(bottom)

    def _select_type(self, combo, entity_type):
        idx = combo.findData(entity_type)
        if idx >= 0:
            combo.setCurrentIndex(idx)

    def _get_entity_names(self, entity_type):
        """按类型取项目中的实体名"""
        if entity_type == "character":
            return [c.name for c in self.project.characters if c.name]
        if entity_type == "location":
            return [l.name for l in self.project.locations if l.name]
        if entity_type == "organization":
            return [o.name for o in self.project.organizations if o.name]
        if entity_type == "item":
            return [i.name for i in self.project.items if i.name]
        if entity_type == "monster":
            return [m.name for m in self.project.monsters if m.name]
        return []

    def _refresh_name_list(self, side):
        if side == "from":
            combo = self.from_name_combo
            type_combo = self.from_type_combo
        else:
            combo = self.to_name_combo
            type_combo = self.to_type_combo

        entity_type = type_combo.currentData()
        names = self._get_entity_names(entity_type)

        current = combo.currentText()
        combo.blockSignals(True)
        combo.clear()
        combo.addItems(names)
        combo.setCurrentText(current or (names[0] if names else ""))
        combo.blockSignals(False)

    def _on_ok(self):
        a_type = self.from_type_combo.currentData()
        a_name = self.from_name_combo.currentText().strip()
        b_type = self.to_type_combo.currentData()
        b_name = self.to_name_combo.currentText().strip()
        t = self.type_combo.currentText().strip()

        if t.startswith("━━"):
            QMessageBox.warning(self, "提示", "请选择具体的关系类型。")
            return
        if not a_name or not b_name:
            QMessageBox.warning(self, "提示", "来源与目标不能为空。")
            return
        if a_type == b_type and a_name == b_name:
            QMessageBox.warning(self, "提示", "来源与目标不能相同。")
            return
        if not t:
            QMessageBox.warning(self, "提示", "关系类型不能为空。")
            return

        a_ep = format_endpoint(a_type, a_name)
        b_ep = format_endpoint(b_type, b_name)

        if not self.relation:
            for r in self.project.relations or []:
                if (r.get("from") == a_ep and r.get("to") == b_ep
                        and r.get("type") == t):
                    QMessageBox.warning(self, "提示", "该关系已存在。")
                    return

        self._result = {
            "from": a_ep,
            "to": b_ep,
            "type": t,
            "description": self.desc_edit.toPlainText().strip(),
        }
        self.accept()

    def get_result(self):
        return self._result


class RelationTab(QWidget):
    def __init__(self, project, parent=None):
        super().__init__(parent)
        self.project = project
        self._updating = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 工具栏
        toolbar = QHBoxLayout()

        self.add_btn = QPushButton("+ 新增关系")
        self.add_btn.clicked.connect(self._on_add)
        toolbar.addWidget(self.add_btn)

        self.del_btn = QPushButton("删除选中")
        self.del_btn.clicked.connect(self._on_delete)
        toolbar.addWidget(self.del_btn)

        self.relayout_btn = QPushButton("重新布局")
        self.relayout_btn.clicked.connect(self._on_relayout)
        toolbar.addWidget(self.relayout_btn)

        self.filter_check = QCheckBox("仅显示有关系的实体")
        self.filter_check.setChecked(True)
        self.filter_check.toggled.connect(lambda _: self._refresh())
        toolbar.addWidget(self.filter_check)

        # 新增：搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索：来源 / 目标 / 类型 / 描述")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setMaximumWidth(280)
        self.search_edit.textChanged.connect(self._on_search_changed)
        toolbar.addWidget(self.search_edit)

        toolbar.addStretch()

        legend = QLabel("● 角色　■ 地点　◇ 组织　◆ 物品　▲ 怪物")
        legend.setProperty("role", "hint")
        toolbar.addWidget(legend)

        layout.addLayout(toolbar)

        # 主体
        splitter = QSplitter(Qt.Horizontal)

        # 表格
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self.count_label = QLabel("关系列表")
        left_layout.addWidget(self.count_label)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["来源", "类型", "目标", "描述"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.doubleClicked.connect(self._on_table_double_clicked)
        self.table.itemSelectionChanged.connect(self._on_table_selection)
        left_layout.addWidget(self.table)

        left.setMinimumWidth(680)
        splitter.addWidget(left)

        # 图
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        self.scene = RelationGraphScene(self)
        self.view = RelationGraphView()
        self.view.setScene(self.scene)
        right_layout.addWidget(self.view)

        splitter.addWidget(right)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self._visible_relations = []  # 当前显示的关系（搜索过滤后）
        self._search_keyword = ""

        self._refresh()

    def _on_search_changed(self, text):
        self._search_keyword = text or ""
        self._refresh()

    def _get_filtered_relations(self):
        """根据搜索关键词过滤关系"""
        relations = list(self.project.relations or [])
        kw = (self._search_keyword or "").strip().lower()
        if not kw:
            return relations

        result = []
        for r in relations:
            haystack = " ".join([
                str(r.get("from", "")),
                str(r.get("to", "")),
                str(r.get("type", "")),
                str(r.get("description", "")),
            ]).lower()
            if kw in haystack:
                result.append(r)
        return result

    def _refresh(self):
        if self._updating:
            return
        self._updating = True

        # 搜索过滤
        self._visible_relations = self._get_filtered_relations()
        relations = self._visible_relations

        # 填充表格
        self.table.setRowCount(len(relations))
        for row, rel in enumerate(relations):
            a_disp = display_endpoint(rel.get("from", ""))
            b_disp = display_endpoint(rel.get("to", ""))
            self.table.setItem(row, 0, QTableWidgetItem(a_disp))
            self.table.setItem(row, 1, QTableWidgetItem(rel.get("type", "")))
            self.table.setItem(row, 2, QTableWidgetItem(b_disp))
            self.table.setItem(row, 3,
                               QTableWidgetItem(rel.get("description", "")))

        total = len(self.project.relations or [])
        shown = len(relations)
        if self._search_keyword.strip():
            self.count_label.setText(
                f"关系列表（匹配 {shown} / 共 {total} 条）"
            )
        else:
            self.count_label.setText(f"关系列表（共 {total} 条）")

        # 图中补孤立角色：仅在"不限制过滤"且无搜索时
        extra_chars = None
        if (not self.filter_check.isChecked()
                and not self._search_keyword.strip()):
            extra_chars = [c.name for c in self.project.characters if c.name]

        self.scene.set_relations(relations, extra_character_names=extra_chars)
        self._updating = False

    def _on_add(self):
        dlg = RelationEditDialog(self.project, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.get_result()
        if data:
            self.project.relations.append(data)
            self._refresh()

    def _on_table_double_clicked(self, index):
        row = index.row()
        if row < 0 or row >= len(self._visible_relations):
            return
        rel = self._visible_relations[row]
        dlg = RelationEditDialog(self.project, relation=rel, parent=self)
        if dlg.exec_() != QDialog.Accepted:
            return
        data = dlg.get_result()
        if data:
            # 用对象身份匹配正式列表中的位置
            try:
                idx = self.project.relations.index(rel)
                self.project.relations[idx] = data
            except ValueError:
                pass
            self._refresh()

    def _on_table_selection(self):
        rows = {idx.row() for idx in self.table.selectedIndexes()}
        selected_keys = set()
        for row in rows:
            if 0 <= row < len(self._visible_relations):
                r = self._visible_relations[row]
                selected_keys.add((
                    r.get("from", ""), r.get("to", ""), r.get("type", "")
                ))
        for edge in self.scene.edges:
            key = (edge.source.endpoint, edge.target.endpoint,
                   edge.relation_type)
            edge.setSelected(key in selected_keys)

    def _on_delete(self):
        rows = sorted({idx.row() for idx in self.table.selectedIndexes()},
                      reverse=True)
        if not rows:
            QMessageBox.information(self, "提示", "请先选中要删除的关系。")
            return
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除选中的 {len(rows)} 条关系吗？"
        )
        if reply != QMessageBox.Yes:
            return
        for row in rows:
            if 0 <= row < len(self._visible_relations):
                rel = self._visible_relations[row]
                try:
                    idx = self.project.relations.index(rel)
                    del self.project.relations[idx]
                except ValueError:
                    pass
        self._refresh()

    def _on_relayout(self):
        self.scene.relayout()

    def refresh(self):
        self._refresh()