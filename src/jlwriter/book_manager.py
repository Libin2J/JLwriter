"""
书籍文件夹管理：book/ 下每个子目录是一本书

目录结构：
    <用户数据目录>/book/
    └── 书名/
        ├── project.json
        ├── project.json.history.json
        ├── meta.json
        └── cover.png / cover.jpg
"""
import os
import json
import shutil
from datetime import datetime

from .paths import get_book_root as _get_book_root


# 兼容旧代码：把模块级 BOOK_ROOT 保留为只读路径
BOOK_ROOT = str(_get_book_root())


def ensure_book_root():
    if not os.path.exists(BOOK_ROOT):
        os.makedirs(BOOK_ROOT, exist_ok=True)


def get_book_root():
    return BOOK_ROOT

def sanitize_folder_name(name):
    if not name:
        return "未命名"
    for ch in '\\/:*?"<>|':
        name = name.replace(ch, "_")
    name = name.strip().strip(".")
    return name or "未命名"


def get_unique_book_dir(title):
    ensure_book_root()
    base = sanitize_folder_name(title)
    candidate = os.path.join(BOOK_ROOT, base)
    if not os.path.exists(candidate):
        return candidate
    i = 2
    while True:
        candidate = os.path.join(BOOK_ROOT, f"{base}_{i}")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def get_project_path(book_dir):
    return os.path.join(book_dir, "project.json")


def get_meta_path(book_dir):
    return os.path.join(book_dir, "meta.json")


def get_cover_path(book_dir):
    for name in ("cover.png", "cover.jpg", "cover.jpeg"):
        p = os.path.join(book_dir, name)
        if os.path.exists(p):
            return p
    return None


def load_meta(book_dir):
    meta_path = get_meta_path(book_dir)
    default = {
        "title": os.path.basename(book_dir),
        "description": "",
        "cover": "",
        "created_at": "",
        "updated_at": "",
        "author": "",
    }
    if not os.path.exists(meta_path):
        return default
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        result = dict(default)
        for k in default:
            if k in data:
                result[k] = data[k]
        return result
    except Exception:
        return default


def save_meta(book_dir, meta):
    meta_path = get_meta_path(book_dir)
    try:
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"保存 meta.json 失败: {e}")


def touch_updated_at(book_dir):
    meta = load_meta(book_dir)
    meta["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    save_meta(book_dir, meta)


def list_books():
    """返回 list[dict]，按 updated_at 降序"""
    ensure_book_root()
    result = []
    for name in os.listdir(BOOK_ROOT):
        book_dir = os.path.join(BOOK_ROOT, name)
        if not os.path.isdir(book_dir):
            continue
        project_file = get_project_path(book_dir)
        if not os.path.exists(project_file):
            continue
        meta = load_meta(book_dir)
        # 若 meta 标题缺失，从 project.json 补充
        if not meta["title"] or meta["title"] == name:
            try:
                with open(project_file, "r", encoding="utf-8") as f:
                    proj = json.load(f)
                meta["title"] = proj.get("title") or name
            except Exception:
                pass
        result.append({
            "dir": book_dir,
            "title": meta["title"] or name,
            "description": meta["description"],
            "cover": get_cover_path(book_dir),
            "created_at": meta["created_at"],
            "updated_at": meta["updated_at"],
            "author": meta["author"],
        })
    result.sort(key=lambda x: x["updated_at"] or "", reverse=True)
    return result


def create_book(title, description=""):
    """创建书籍文件夹 + 空 project.json，返回 (book_dir, project_path)"""
    from .models import StoryProject
    ensure_book_root()
    book_dir = get_unique_book_dir(title)
    os.makedirs(book_dir, exist_ok=True)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    meta = {
        "title": title,
        "description": description,
        "cover": "",
        "created_at": now,
        "updated_at": now,
        "author": "",
    }
    save_meta(book_dir, meta)

    project_path = get_project_path(book_dir)
    empty_project = StoryProject(title=title)
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(empty_project.to_dict(), f, ensure_ascii=False, indent=2)

    return book_dir, project_path


def delete_book(book_dir):
    if not os.path.isdir(book_dir):
        return False
    try:
        shutil.rmtree(book_dir)
        return True
    except Exception as e:
        print(f"删除失败: {e}")
        return False


def import_external_project(source_json_path):
    """导入外部 project.json 到 book 文件夹"""
    if not os.path.exists(source_json_path):
        return None, None
    try:
        with open(source_json_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None, None

    title = data.get("title") or os.path.splitext(
        os.path.basename(source_json_path)
    )[0]
    book_dir, project_path = create_book(title)

    try:
        with open(project_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        return None, None

    # 复制历史文件（若存在）
    src_history = source_json_path + ".history.json"
    if os.path.exists(src_history):
        try:
            shutil.copy2(src_history, project_path + ".history.json")
        except Exception:
            pass

    return book_dir, project_path


def set_cover(book_dir, source_image_path):
    if not os.path.exists(source_image_path):
        return False
    ext = os.path.splitext(source_image_path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg"):
        return False
    for name in ("cover.png", "cover.jpg", "cover.jpeg"):
        old = os.path.join(book_dir, name)
        if os.path.exists(old):
            try:
                os.remove(old)
            except Exception:
                pass
    dst = os.path.join(book_dir, "cover" + ext)
    try:
        shutil.copy2(source_image_path, dst)
        meta = load_meta(book_dir)
        meta["cover"] = "cover" + ext
        save_meta(book_dir, meta)
        return True
    except Exception:
        return False


def remove_cover(book_dir):
    for name in ("cover.png", "cover.jpg", "cover.jpeg"):
        p = os.path.join(book_dir, name)
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    meta = load_meta(book_dir)
    meta["cover"] = ""
    save_meta(book_dir, meta)