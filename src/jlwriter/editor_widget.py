"""
写作助手编辑页面
"""
from PyQt5.QtWidgets import QPlainTextEdit
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QTextCursor, QTextDocument, QTextBlockFormat, QTextCharFormat


class EditorWidget(QPlainTextEdit):
    contentModified = pyqtSignal()
    inputMethodActivated = pyqtSignal(bool)  # 新增：输入法激活/结束信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_chapter = None
        self.current_volume = None
        self.setPlaceholderText("选择一个章节开始写作...")
        self.textChanged.connect(self._on_text_changed)

    def load_chapter(self, vol, ch):
        self.current_volume = vol
        self.current_chapter = ch
        self.blockSignals(True)
        self.setPlainText(ch.content)
        self.blockSignals(False)
        self.setReadOnly(False)
        self.setPlaceholderText("")
        self._apply_paragraph_spacing()

    def _apply_paragraph_spacing(self):
        doc = self.document()
        if doc.isEmpty():
            return
        fmt = QTextBlockFormat()
        fmt.setTopMargin(6)
        fmt.setBottomMargin(0)
        block = doc.firstBlock()
        while block.isValid():
            cursor = QTextCursor(block)
            cursor.setBlockFormat(fmt)
            block = block.next()

    def clear_editor(self, vol=None):
        self.current_chapter = None
        self.current_volume = vol
        self.blockSignals(True)
        self.clear()
        if vol:
            self.setPlaceholderText(f"分卷: {vol.title}\n(选中章节进行编辑)")
        else:
            self.setPlaceholderText("选择一个章节开始写作...")
        self.setReadOnly(True)
        self.blockSignals(False)

    def _on_text_changed(self):
        if self.current_chapter:
            self.current_chapter.content = self.toPlainText()
        self.contentModified.emit()

    def keyPressEvent(self, event):
        if not self.isReadOnly() and self.current_chapter is not None:
            if event.key() == Qt.Key_Tab:
                self.textCursor().insertText("　　")
                return
            if event.key() in (Qt.Key_Return, Qt.Key_Enter):
                # 先换行
                QPlainTextEdit.keyPressEvent(self, event)
                # 重置格式，避免继承 ghost 灰色
                cursor = self.textCursor()
                cursor.setCharFormat(QTextCharFormat())
                cursor.insertText("    ")
                return
        QPlainTextEdit.keyPressEvent(self, event)

    # ---------- 查找功能保持不变 ----------
    def find_text(self, text, case_sensitive=False, wrap=True):
        flags = QTextDocument.FindFlag(0)
        if case_sensitive:
            flags = QTextDocument.FindCaseSensitively
        cursor = self.textCursor()
        if cursor.hasSelection():
            cursor.setPosition(cursor.selectionEnd())
        self.setTextCursor(cursor)
        found = self.find(text, flags)
        if not found and wrap:
            self.moveCursor(QTextCursor.Start)
            found = self.find(text, flags)
        return found

    def find_first(self, text, case_sensitive=False):
        self.moveCursor(QTextCursor.Start)
        return self.find_text(text, case_sensitive, wrap=False)

    def find_next(self, text, case_sensitive=False):
        return self.find_text(text, case_sensitive, wrap=True)

    def replace(self, search_text, replace_text, case_sensitive=False):
        cursor = self.textCursor()
        if cursor.hasSelection() and cursor.selectedText() == search_text:
            cursor.insertText(replace_text)
            return True
        if self.find_next(search_text, case_sensitive):
            self.textCursor().insertText(replace_text)
            return True
        return False

    def replace_all(self, search_text, replace_text, case_sensitive=False):
        count = 0
        self.moveCursor(QTextCursor.Start)
        while self.find_text(search_text, case_sensitive, wrap=False):
            self.textCursor().insertText(replace_text)
            count += 1
        return count

    def set_editor_font(self, family=None, size=None):
        font = self.font()
        if family:
            font.setFamily(family)
        if size:
            font.setPointSize(size)
        self.setFont(font)

    def inputMethodEvent(self, event):
        # 通知 GhostTextHandler 输入法已激活/结束
        self.inputMethodActivated.emit(True)  # 激活
        super().inputMethodEvent(event)
        self.inputMethodActivated.emit(False)  # 结束