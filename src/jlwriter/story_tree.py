"""
章节、分卷树形图定义
"""
from PyQt5.QtWidgets import (
    QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog,
    QMessageBox, QAbstractItemView
)
from PyQt5.QtCore import pyqtSignal, Qt
from .models import StoryProject, Chapter

class StoryTree(QTreeWidget):
    """显示分卷和章节的树形控件"""
    chapterSelected = pyqtSignal(object, object)   # (volume, chapter) 或 (volume, None)
    structureChanged = pyqtSignal()  # 新增组件更改信号
    chapterPlanRequested = pyqtSignal(int, int)  # 新增：(vol_idx, ch_idx)
    chapterDeviationRequested = pyqtSignal(int, int)  # 新增章节与规划分析
    chapterExportRequested = pyqtSignal(int, int)  # 新增导出

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(3)  # 自定义右键菜单
        self.customContextMenuRequested.connect(self.show_context_menu)
        # 关键改动：同时响应鼠标点击与键盘方向键
        self.currentItemChanged.connect(self._on_current_item_changed)
        self.setIndentation(10)

        # 新增：支持 Ctrl/Shift 多选，且整行选中
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)

        self.project = StoryProject()
        self._volume_summaries = {}
        self._suppress_signals = False  # 重建期间阻断信号，避免误触发

    def load_project(self, project: StoryProject):
        self.project = project
        # 切换项目时清空选中
        self.refresh(keep_selection=False)

    def refresh(self, select_vol=-1, select_ch=-1, keep_selection=True):
        """
        重建章节树。
        - select_vol / select_ch：显式指定选中位置
        - keep_selection：未显式指定时，是否保留原选中
        """
        # 未指定时，尝试沿用当前选中
        if select_vol < 0 and keep_selection:
            cur = self.currentItem()
            if cur:
                data = cur.data(0, Qt.UserRole)
                if data:
                    if data[0] == "volume":
                        select_vol, select_ch = data[1], -1
                    elif data[0] == "chapter":
                        select_vol, select_ch = data[1], data[2]

        self._suppress_signals = True
        self.clear()

        target = None
        for i, vol in enumerate(self.project.volumes):
            vol_item = QTreeWidgetItem(self, [vol.title])
            vol_item.setData(0, Qt.UserRole, ("volume", i))
            if select_vol == i and select_ch < 0:
                target = vol_item

            for j, ch in enumerate(vol.chapters):
                has_plan = bool(getattr(ch, "plan", None))
                marker = "◆" if has_plan else "○"
                ch_item = QTreeWidgetItem(vol_item, [f"{marker} {ch.title}"])
                ch_item.setData(0, Qt.UserRole, ("chapter", i, j))
                if has_plan and ch.plan.goal:
                    ch_item.setToolTip(0, ch.plan.goal[:120])
                if select_vol == i and select_ch == j:
                    target = ch_item

            self.expandAll()

        self._suppress_signals = False

        if target:
            self.setCurrentItem(target)
            self.scrollToItem(target)

    def _on_current_item_changed(self, current, previous):
        """鼠标点击或键盘方向键切换 currentItem 时触发"""
        if self._suppress_signals or current is None:
            return
        self._emit_chapter_selected(current)

    def _emit_chapter_selected(self, item):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        if data[0] == "volume":
            idx = data[1]
            if 0 <= idx < len(self.project.volumes):
                self.chapterSelected.emit(self.project.volumes[idx], None)
        elif data[0] == "chapter":
            idx_vol, idx_ch = data[1], data[2]
            if 0 <= idx_vol < len(self.project.volumes):
                vol = self.project.volumes[idx_vol]
                if 0 <= idx_ch < len(vol.chapters):
                    self.chapterSelected.emit(vol, vol.chapters[idx_ch])

    def show_context_menu(self, pos):
        items = self.selectedItems()
        menu = QMenu(self)

        # 多选：优先显示批量操作
        if len(items) >= 2:
            chapter_count = 0
            volume_count = 0
            for it in items:
                data = it.data(0, Qt.UserRole)
                if not data:
                    continue
                if data[0] == "volume":
                    volume_count += 1
                elif data[0] == "chapter":
                    chapter_count += 1

            label_parts = []
            if volume_count:
                label_parts.append(f"{volume_count} 个分卷")
            if chapter_count:
                label_parts.append(f"{chapter_count} 个章节")
            summary = " 和 ".join(label_parts) if label_parts else f"{len(items)} 项"

            menu.addAction(
                f"批量删除选中的 {summary}",
                self.delete_selected_items
            )
            menu.exec_(self.viewport().mapToGlobal(pos))
            return

        # 单选：原有逻辑
        item = self.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return

        if data[0] == "volume":
            menu.addAction("重命名分卷", lambda: self.rename_item(item))
            menu.addAction("添加章节", lambda: self.add_chapter(item))
            menu.addAction("删除分卷", lambda: self.delete_item(item))
        elif data[0] == "chapter":
            v_idx, c_idx = data[1], data[2]
            menu.addAction(
                "编辑章节规划",
                lambda: self.chapterPlanRequested.emit(v_idx, c_idx)
            )
            menu.addAction(
                "对比规划与实际",
                lambda: self.chapterDeviationRequested.emit(v_idx, c_idx)
            )
            menu.addSeparator()
            menu.addAction(
                "导出本章...",
                lambda: self.chapterExportRequested.emit(v_idx, c_idx)
            )
            menu.addSeparator()
            menu.addAction("重命名章节", lambda: self.rename_item(item))
            menu.addAction("删除章节", lambda: self.delete_item(item))
        menu.exec_(self.viewport().mapToGlobal(pos))

    def delete_selected_items(self):
        items = self.selectedItems()
        if len(items) < 2:
            return

        # 1) 收集要删除的卷索引
        vol_to_delete = set()
        for it in items:
            data = it.data(0, Qt.UserRole)
            if data and data[0] == "volume":
                vol_to_delete.add(data[1])

        # 2) 收集要删除的章节，跳过其父卷已被选中的章节
        chapters_by_vol = {}   # vol_idx -> set(ch_idx)
        for it in items:
            data = it.data(0, Qt.UserRole)
            if not data or data[0] != "chapter":
                continue
            v_idx, c_idx = data[1], data[2]
            if v_idx in vol_to_delete:
                continue
            chapters_by_vol.setdefault(v_idx, set()).add(c_idx)

        if not vol_to_delete and not chapters_by_vol:
            return

        total_vol = len(vol_to_delete)
        total_ch = sum(len(s) for s in chapters_by_vol.values())

        # 3) 确认
        parts = []
        if total_vol:
            parts.append(f"{total_vol} 个分卷（含其中全部章节）")
        if total_ch:
            parts.append(f"{total_ch} 个章节")
        msg = (
            "确定要删除选中的 " + " 和 ".join(parts) + " 吗？\n"
            "此操作不可撤销。"
        )
        reply = QMessageBox.question(
            self, "确认批量删除", msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        # 4) 先删章节（每卷内从后往前删，避免索引偏移）
        for v_idx, ch_set in chapters_by_vol.items():
            if v_idx < 0 or v_idx >= len(self.project.volumes):
                continue
            vol = self.project.volumes[v_idx]
            for c_idx in sorted(ch_set, reverse=True):
                if 0 <= c_idx < len(vol.chapters):
                    del vol.chapters[c_idx]

        # 5) 再删卷（从后往前删）
        for v_idx in sorted(vol_to_delete, reverse=True):
            if 0 <= v_idx < len(self.project.volumes):
                del self.project.volumes[v_idx]

        # 6) 刷新并通知
        self.refresh()
        self.structureChanged.emit()

    def rename_item(self, item):
        data = item.data(0, Qt.UserRole)   # 改为 Qt.UserRole
        if not data:
            return
        old = item.text(0)
        new, ok = QInputDialog.getText(self, "重命名", "新名称:", text=old)
        if ok and new:
            item.setText(0, new)
            if data[0] == "volume":
                idx = data[1]
                self.project.volumes[idx].title = new
            elif data[0] == "chapter":
                v_idx, c_idx = data[1], data[2]
                self.project.volumes[v_idx].chapters[c_idx].title = new

    def add_chapter(self, volume_item=None):
        if not volume_item:
            items = self.selectedItems()
            if items:
                volume_item = items[0]
            else:
                return
        data = volume_item.data(0, Qt.UserRole)
        if not data:
            return
        # 允许在卷或章节上右键
        if data[0] == "volume":
            v_idx = data[1]
        elif data[0] == "chapter":
            v_idx = data[1]
        else:
            return

        name, ok = QInputDialog.getText(self, "新建章节", "章节名称:")
        if not (ok and name.strip()):
            return
        name = name.strip()

        vol = self.project.volumes[v_idx]
        vol.chapters.append(Chapter(title=name))
        new_ch_idx = len(vol.chapters) - 1

        # 关键：refresh 定位到新章节，会触发 chapterSelected
        self.refresh(select_vol=v_idx, select_ch=new_ch_idx)
        self.structureChanged.emit()

    def delete_item(self, item):
        data = item.data(0, Qt.UserRole)   # 改为 Qt.UserRole
        if not data:
            return
        if data[0] == "volume":
            idx = data[1]
            del self.project.volumes[idx]
        elif data[0] == "chapter":
            v_idx, c_idx = data[1], data[2]
            del self.project.volumes[v_idx].chapters[c_idx]
        self.refresh()
        self.structureChanged.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.RightButton:
            item = self.itemAt(event.pos())
            if item is not None and item not in self.selectedItems():
                # 点中未选中项：清空旧选区，选中该项
                self.clearSelection()
                item.setSelected(True)
                self.setCurrentItem(item)
            # 点中已选中项：保持现有选区不变
        super().mousePressEvent(event)