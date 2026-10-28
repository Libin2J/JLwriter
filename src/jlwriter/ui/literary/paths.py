"""设计系统自己的资源目录解析。

刻意不依赖 ``jlwriter.paths``，这样整个 ``literary`` 目录可以原样复制到
其它 PyQt5 项目。优先级：

1. ``JLWRITER_UI_DATA_DIR``
2. ``JLWRITER_DATA_DIR``（与主程序共用，便于测试）
3. 系统用户数据目录下的 ``jlwriter``
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def user_data_dir() -> Path:
    override = os.environ.get("JLWRITER_UI_DATA_DIR") or os.environ.get(
        "JLWRITER_DATA_DIR"
    )
    if override:
        root = Path(override).expanduser()
    elif sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.environ.get("LOCALAPPDATA") or str(Path.home())
        root = Path(base) / "jlwriter"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support" / "jlwriter"
    else:
        base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
        root = Path(base) / "jlwriter"
    root.mkdir(parents=True, exist_ok=True)
    return root


def asset_dir() -> Path:
    folder = user_data_dir() / "ui-assets"
    folder.mkdir(parents=True, exist_ok=True)
    return folder
