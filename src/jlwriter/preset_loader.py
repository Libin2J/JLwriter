"""
预设加载器：读取 presetting.json

读取策略：
- 包内 presetting.json：内置预设
- 用户数据目录 presetting.json：用户自定义预设
- 加载时合并：同 name 用户优先覆盖内置

保存策略：
- 只写入用户数据目录，不修改包内文件
"""
import json
import uuid
from pathlib import Path

from .paths import (
    get_package_resource,
    get_preset_user_path,
)


# ============================================================
# 底层读写
# ============================================================

def _empty_data():
    return {"version": 1, "presets": []}


def _load_raw(path: Path) -> dict:
    if not path.exists():
        return _empty_data()
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return _empty_data()
    if not isinstance(data, dict):
        return _empty_data()
    if not isinstance(data.get("presets"), list):
        data["presets"] = []
    return data


def _save_raw(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _valid_preset(p) -> bool:
    return isinstance(p, dict) and bool((p.get("name") or "").strip())


# ============================================================
# 加载：合并内置与用户
# ============================================================

def load_presets():
    """
    读取所有预设。
    - 先加载包内内置预设
    - 再加载用户自定义预设
    - 同 name 用户覆盖内置
    """
    builtin_path = get_package_resource("presetting.json")
    user_path = get_preset_user_path()

    builtin = [
        p for p in _load_raw(builtin_path).get("presets", [])
        if _valid_preset(p)
    ]
    user = [
        p for p in _load_raw(user_path).get("presets", [])
        if _valid_preset(p)
    ]

    merged = {}
    order = []
    for p in builtin:
        name = (p.get("name") or "").strip()
        merged[name] = p
        if name not in order:
            order.append(name)
    for p in user:
        name = (p.get("name") or "").strip()
        merged[name] = p
        if name not in order:
            order.append(name)

    return [merged[name] for name in order if name in merged]



# ============================================================
# 用户预设：保存 / 列出 / 删除
# ============================================================


def save_user_preset(preset: dict) -> bool:
    """
    保存用户预设到用户数据目录。
    - 同 name 已存在：覆盖（保留原 id）
    - 不存在：新增（生成新 id）
    返回是否成功。
    """
    name = (preset.get("name") or "").strip()
    if not name:
        return False

    user_path = get_preset_user_path()
    data = _load_raw(user_path)

    new_preset = dict(preset)
    new_preset["name"] = name

    existing_idx = None
    for i, p in enumerate(data["presets"]):
        if isinstance(p, dict) and (p.get("name") or "").strip() == name:
            existing_idx = i
            break

    if existing_idx is not None:
        old_id = data["presets"][existing_idx].get("id", "")
        if old_id and not new_preset.get("id"):
            new_preset["id"] = old_id
        data["presets"][existing_idx] = new_preset
    else:
        if not new_preset.get("id"):
            new_preset["id"] = f"user_{uuid.uuid4().hex[:8]}"
        data["presets"].append(new_preset)

    try:
        _save_raw(user_path, data)
        return True
    except Exception:
        return False


def delete_user_preset(preset_id: str) -> bool:
    """按 id 删除用户预设"""
    if not preset_id:
        return False
    user_path = get_preset_user_path()
    data = _load_raw(user_path)
    before = len(data["presets"])
    data["presets"] = [
        p for p in data["presets"]
        if not (isinstance(p, dict) and p.get("id") == preset_id)
    ]
    if len(data["presets"]) == before:
        return False
    try:
        _save_raw(user_path, data)
        return True
    except Exception:
        return False


def is_user_preset(preset: dict) -> bool:
    """判断某预设是否来自用户目录（通过 id 前缀识别）"""
    pid = (preset or {}).get("id", "")
    return str(pid).startswith("user_")