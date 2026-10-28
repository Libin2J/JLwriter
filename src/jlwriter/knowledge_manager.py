"""
知识库管理：读取 knowledge/ 目录下的 md 文件

文件格式约定：
    ## 人物描写
    - 案例1
    - 案例2

    ## 对话描写
    - 案例1

    ## 环境描写
    - 案例1
"""
import os
"""
知识库管理：读取 knowledge/ 下的 md 文件

读取优先级（同名文件用户覆盖内置）：
1. 用户数据目录下的 knowledge/（用户自定义）
2. 包内的 knowledge/（内置示例）

文件格式约定：
    ## 人物描写
    - 案例1
    - 案例2

    ## 对话描写
    - 案例1

    ## 环境描写
    - 案例1
"""
import os
import re
import random

from .paths import (
    get_knowledge_user_dir,
    get_package_resource_dir,
)


AI_STYLE_FILE = "ai_style.md"

SECTION_CHARACTER = "人物描写"
SECTION_DIALOGUE = "对话描写"
SECTION_ENVIRONMENT = "环境描写"

DEFAULT_SECTIONS = [SECTION_CHARACTER, SECTION_DIALOGUE, SECTION_ENVIRONMENT]


# ============================================================
# 目录
# ============================================================

def _get_user_dir() -> str:
    return str(get_knowledge_user_dir())


def _get_builtin_dir() -> str:
    return str(get_package_resource_dir("knowledge"))




# ============================================================
# 文件列表
# ============================================================

def _iter_search_dirs():
    """用户目录优先，其次内置目录"""
    for d in (_get_user_dir(), _get_builtin_dir()):
        if os.path.isdir(d):
            yield d


def _resolve_style_file(file_name: str) -> str:
    """按优先级查找某个 md 文件，返回实际路径；找不到返回空串"""
    for d in _iter_search_dirs():
        p = os.path.join(d, file_name)
        if os.path.isfile(p):
            return p
    return ""


def list_style_files():
    """列出所有可用的文笔模板文件（内置 + 用户，同名用户优先）"""
    result = []
    seen = set()

    for d in _iter_search_dirs():
        try:
            names = sorted(os.listdir(d))
        except OSError:
            continue
        for name in names:
            if not name.lower().endswith(".md"):
                continue
            if name == AI_STYLE_FILE:
                continue
            if name in seen:
                continue
            path = os.path.join(d, name)
            if not os.path.isfile(path):
                continue
            seen.add(name)
            result.append({
                "name": name,
                "display": os.path.splitext(name)[0],
                "path": path,
                "source": "user" if d == _get_user_dir() else "builtin",
            })
    return result


def ai_style_exists() -> bool:
    return bool(_resolve_style_file(AI_STYLE_FILE))


# ============================================================
# 读取
# ============================================================

def _read_file(path: str) -> str:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def parse_sections(content):
    """解析 md 文件，返回 {section_name: [line1, line2, ...]}"""
    sections = {}
    current = None
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        m = re.match(r'^#{1,4}\s+(.+)$', stripped)
        if m:
            title = m.group(1).strip()
            current = title
            sections.setdefault(current, [])
            continue

        if current is None:
            continue

        text = re.sub(r'^[-*+]\s+', '', stripped)
        text = text.strip()
        if text:
            sections[current].append(text)
    return sections


def load_ai_style_template() -> str:
    """加载 AI 味去除模板（全部内容）"""
    path = _resolve_style_file(AI_STYLE_FILE)
    if not path:
        return ""
    return _read_file(path).strip()


def load_style_sample(file_name, per_section=10):
    """加载某个文笔模板文件，每节随机抽取 per_section 条"""
    path = _resolve_style_file(file_name)
    if not path:
        return {}
    content = _read_file(path)
    sections = parse_sections(content)
    result = {}
    for name, lines in sections.items():
        if not lines:
            continue
        k = min(per_section, len(lines))
        result[name] = random.sample(lines, k)
    return result


