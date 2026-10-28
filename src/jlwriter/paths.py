"""
统一路径管理：用户数据目录（可写）与包内资源（只读）

用户数据目录：
    Windows: %APPDATA%/jlwriter/
    macOS:   ~/Library/Application Support/jlwriter/
    Linux:   $XDG_DATA_HOME/jlwriter/ 或 ~/.local/share/jlwriter/
    可通过环境变量 JLWRITER_DATA_DIR 覆盖，便于测试

包内资源：
    通过 importlib.resources 读取，pip install 后指向 site-packages/jlwriter/
    开发环境（直接运行）时回退到源码目录
"""
import os
import sys
from pathlib import Path


APP_NAME = "jlwriter"


# ============================================================
# 用户数据目录（可写）
# ============================================================

def get_user_data_dir() -> Path:
    env_override = os.environ.get("JLWRITER_DATA_DIR")
    if env_override:
        root = Path(env_override).expanduser().resolve()
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA")
        if not base:
            base = str(Path.home())
        root = Path(base) / APP_NAME
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        xdg = os.environ.get("XDG_DATA_HOME")
        if xdg:
            root = Path(xdg) / APP_NAME
        else:
            root = Path.home() / ".local" / "share" / APP_NAME

    root.mkdir(parents=True, exist_ok=True)
    return root


def get_book_root() -> Path:
    return get_user_data_dir() / "book"


def get_knowledge_user_dir() -> Path:
    d = get_user_data_dir() / "knowledge"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_preset_user_path() -> Path:
    return get_user_data_dir() / "presetting.json"


# ============================================================
# 包内只读资源（关键修复）
# ============================================================

def _package_root() -> Path:
    """
    包内根目录，优先级：
    1. PyInstaller 打包后：sys._MEIPASS / jlwriter（或 _MEIPASS 根）
    2. 正常环境：用 importlib.util.find_spec 定位 jlwriter 包，不做真正 import
    3. 兜底：paths.py 自身的父目录
    """
    # 1) PyInstaller
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / "jlwriter"
            if (candidate / "presetting.json").exists():
                return candidate
            if (Path(meipass) / "presetting.json").exists():
                return Path(meipass)
        exe_dir = Path(sys.executable).resolve().parent
        candidate = exe_dir / "jlwriter"
        if (candidate / "presetting.json").exists():
            return candidate

    # 2) 正常环境：find_spec 只查找，不实际 import，避免循环导入
    try:
        import importlib.util
        spec = importlib.util.find_spec("jlwriter")
        if spec and spec.origin:
            root = Path(spec.origin).resolve().parent
            if root.exists():
                return root
    except Exception:
        pass

    # 3) 兜底
    return Path(__file__).resolve().parent


def get_package_resource(name: str) -> Path:
    return _package_root() / name


def get_package_resource_dir(name: str) -> Path:
    return _package_root() / name


def get_icon_file() -> Path:
    return get_package_resource("ico/robot.ico")

def get_app_icon_file() -> Path:
    """应用主图标（窗口 / 任务栏 / 桌面快捷方式）"""
    return get_package_resource("ico/jlwriter.png")