"""
JLwriter 入口
"""
import sys

from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt5.QtCore import Qt, QSettings, QLibraryInfo, QTranslator

from .main_window import MainWindow
from .theme_manager import ThemeManager
from .ui.literary import install as install_literary_theme
from .paths import get_app_icon_file


APP_USER_MODEL_ID = "JLwriter.Desktop.1"
THEME_SETTINGS_KEY = "ui/theme"


def load_app_icon() -> QIcon:
    """
    优先加载 ico/jlwriter.png；
    若文件不存在或加载失败，回退到程序化绘制的图标。
    """
    icon_path = get_app_icon_file()
    if icon_path.exists():
        pixmap = QPixmap(str(icon_path))
        if not pixmap.isNull():
            return QIcon(pixmap)

    return _create_fallback_icon()


def _create_fallback_icon() -> QIcon:
    """程序化绘制的备用图标：绿色圆形背景 + 白色字母 JL"""
    pixmap = QPixmap(256, 256)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)

    # 圆形背景
    painter.setBrush(QColor("#4CAF80"))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(16, 16, 224, 224)

    # 字母 JL
    painter.setPen(Qt.white)
    font = QFont("Arial", 104, QFont.Bold)
    font.setLetterSpacing(QFont.AbsoluteSpacing, -8)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "JL")

    painter.end()
    return QIcon(pixmap)


def _set_windows_app_id():
    """
    Windows 任务栏图标独立化：
    不设置 AppUserModelID 时，任务栏会显示 python.exe 的图标，
    而不是我们设置的 QIcon。只在 Windows 上生效，失败时静默跳过。
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            APP_USER_MODEL_ID
        )
    except Exception:
        pass


def _saved_theme() -> str:
    """上次使用的主题（全局），没有则用书卷。"""
    try:
        settings = QSettings("JLwriter", "JLwriter")
        return ThemeManager.theme_key(settings.value(THEME_SETTINGS_KEY, "book"))
    except Exception:
        return ThemeManager.theme_key("book")


def _install_translator(app: QApplication):
    """让 QMessageBox / QFileDialog 的标准按钮显示中文。"""
    translator = QTranslator(app)
    path = QLibraryInfo.location(QLibraryInfo.TranslationsPath)
    for name in ("qtbase_zh_CN", "qt_zh_CN"):
        if translator.load(name, path):
            app.installTranslator(translator)
            app._qt_translator = translator  # 防止被回收
            return translator
    return None


def main():
    # 必须在 QApplication 创建前调用，否则 Windows 任务栏图标不生效
    _set_windows_app_id()

    # 高 DPI：让文学风字号与留白在缩放屏上保持一致
    for attribute in (Qt.AA_EnableHighDpiScaling, Qt.AA_UseHighDpiPixmaps):
        try:
            QApplication.setAttribute(attribute, True)
        except Exception:
            pass

    app = QApplication(sys.argv)
    app.setApplicationName("JLwriter")
    app.setOrganizationName("JLwriter")
    _install_translator(app)

    icon = load_app_icon()
    app.setWindowIcon(icon)

    install_literary_theme(app, _saved_theme())

    window = MainWindow()
    window.setWindowIcon(icon)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()