"""
档案提取差异计算：将 AI 提取结果与现有档案对比，生成"新增 / 补充"清单
"""


# ============================================================
# 差异计算
# ============================================================

def compute_extraction_diff(project, extracted):
    """
    计算提取结果与现有档案的差异。
    返回结构：
    {
        "characters":    {"new": [...], "supplement": [{"name", "fields": [...]}]},
        "relations":     {"new": [...]},
        "locations":     {"new": [...], "supplement": [...]},
        "organizations": {"new": [...], "supplement": [...]},
        "items":         {"new": [...], "supplement": [...]},
    }
    """
    return {
        "characters": _diff_characters(
            project, extracted.get("characters") or []
        ),
        "monsters": _diff_monsters(
            project, extracted.get("monsters") or []
        ),
        "relations": _diff_relations(
            project, extracted.get("relations") or []
        ),
        "locations": _diff_locations(
            project, extracted.get("locations") or []
        ),
        "organizations": _diff_organizations(
            project, extracted.get("organizations") or []
        ),
        "items": _diff_items(
            project, extracted.get("items") or []
        ),
    }


def _is_empty(v):
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, dict)):
        return len(v) == 0
    return False


def _diff_characters(project, characters):
    existing = {c.name: c for c in project.characters}
    new_items, supplement_items = [], []

    for item in characters:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        if name not in existing:
            new_items.append(item)
            continue

        target = existing[name]
        fields = []
        for field, key, label in [
            ("appearance", "appearance", "外貌"),
            ("personality", "personality", "性格"),
            ("habits", "habits", "习惯"),
        ]:
            new_val = (item.get(key) or "").strip()
            if new_val and _is_empty(getattr(target, field)):
                fields.append({"field": field, "label": label,
                               "value": new_val})

        # 状态字段：新值非空且与旧值不同 → 算更新
        for field, key, label in [
            ("age", "age", "年龄"),
            ("power_level", "power_level", "力量等级"),
            ("emotion", "emotion", "情绪"),
            ("health", "health", "健康状况"),
            ("status_notes", "status_notes", "其他状态"),
        ]:
            new_val = (item.get(key) or "").strip()
            old_val = (getattr(target, field, "") or "").strip()
            if new_val and new_val != old_val:
                fields.append({
                    "field": field,
                    "label": label,
                    "value": new_val,
                    "old_value": old_val,
                    "is_status": True,
                })

        new_aliases = [
            str(a).strip() for a in (item.get("aliases") or [])
            if str(a).strip() and str(a).strip() != target.name
            and str(a).strip() not in target.aliases
        ]
        if new_aliases:
            fields.append({"field": "aliases", "label": "别名",
                           "value": new_aliases, "is_list": True})

        new_events = [
            str(ev).strip() for ev in (item.get("timeline_events") or [])
            if str(ev).strip() and str(ev).strip() not in target.timeline
        ]
        if new_events:
            fields.append({"field": "timeline", "label": "时间线",
                           "value": new_events, "is_list": True})

        if fields:
            supplement_items.append({
                "name": name, "fields": fields, "raw": item,
            })

    return {"new": new_items, "supplement": supplement_items}

def _diff_monsters(project, monsters):
    existing = {m.name: m for m in project.monsters}
    new_items, supplement_items = [], []

    for item in monsters:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        if name not in existing:
            new_items.append(item)
            continue

        target = existing[name]
        fields = []
        for field, key, label in [
            ("appearance", "appearance", "外形"),
            ("behavior_ability", "behavior_ability", "行为与能力"),
            ("category", "category", "纲目"),
        ]:
            new_val = (item.get(key) or "").strip()
            if new_val and _is_empty(getattr(target, field)):
                fields.append({"field": field, "label": label,
                               "value": new_val})

        new_aliases = [
            str(a).strip() for a in (item.get("aliases") or [])
            if str(a).strip() and str(a).strip() != target.name
            and str(a).strip() not in target.aliases
        ]
        if new_aliases:
            fields.append({"field": "aliases", "label": "别名",
                           "value": new_aliases, "is_list": True})

        if fields:
            supplement_items.append({
                "name": name, "fields": fields, "raw": item,
            })

    return {"new": new_items, "supplement": supplement_items}

def _diff_relations(project, relations):
    existing_keys = set()
    for r in project.relations or []:
        existing_keys.add((
            r.get("from", ""),
            r.get("to", ""),
            r.get("type", ""),
        ))

    new_items = []
    for rel in relations:
        if not isinstance(rel, dict):
            continue
        key = (
            (rel.get("from") or "").strip(),
            (rel.get("to") or "").strip(),
            (rel.get("type") or "").strip() or "关系",
        )
        if not key[0] or not key[1] or key[0] == key[1]:
            continue
        if key not in existing_keys:
            new_items.append(rel)
            existing_keys.add(key)

    return {"new": new_items}


def _diff_locations(project, locations):
    existing = {l.name: l for l in project.locations}
    new_items, supplement_items = [], []

    for item in locations:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        if name not in existing:
            new_items.append(item)
            continue

        target = existing[name]
        fields = []
        for field, key, label in [
            ("level", "level", "层级"),
            ("parent", "parent", "上级地点"),
            ("description", "description", "描述"),
        ]:
            new_val = (item.get(key) or "").strip()
            if new_val and _is_empty(getattr(target, field)):
                fields.append({"field": field, "label": label,
                               "value": new_val})

        if fields:
            supplement_items.append({
                "name": name, "fields": fields, "raw": item,
            })

    return {"new": new_items, "supplement": supplement_items}


def _diff_organizations(project, organizations):
    existing = {o.name: o for o in project.organizations}
    new_items, supplement_items = [], []

    for item in organizations:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        if name not in existing:
            new_items.append(item)
            continue

        target = existing[name]
        fields = []
        for field, key, label in [
            ("nature", "nature", "性质"),
            ("description", "description", "描述"),
        ]:
            new_val = (item.get(key) or "").strip()
            if new_val and _is_empty(getattr(target, field)):
                fields.append({"field": field, "label": label,
                               "value": new_val})

        new_members = [
            str(m).strip() for m in (item.get("members") or [])
            if str(m).strip() and str(m).strip() not in target.members
        ]
        if new_members:
            fields.append({"field": "members", "label": "成员",
                           "value": new_members, "is_list": True})

        if fields:
            supplement_items.append({
                "name": name, "fields": fields, "raw": item,
            })

    return {"new": new_items, "supplement": supplement_items}


def _diff_items(project, items):
    existing = {i.name: i for i in project.items}
    new_items, supplement_items = [], []

    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        if name not in existing:
            new_items.append(item)
            continue

        target = existing[name]
        fields = []
        for field, key, label in [
            ("type", "type", "类型"),
            ("description", "description", "描述"),
            ("ability", "ability", "能力"),
            ("owner", "owner", "归属"),
        ]:
            new_val = (item.get(key) or "").strip()
            if new_val and _is_empty(getattr(target, field)):
                fields.append({"field": field, "label": label,
                               "value": new_val})

        if fields:
            supplement_items.append({
                "name": name, "fields": fields, "raw": item,
            })

    return {"new": new_items, "supplement": supplement_items}


# ============================================================
# 应用
# ============================================================

def apply_selected(project, extracted, selected):
    """
    只应用 selected 中勾选的项目。
    selected: {
        "characters_new": set of names,
        "characters_supplement": set of names,
        "relations_new": set of (from, to, type),
        "locations_new": set of names,
        "locations_supplement": set of names,
        "organizations_new": set of names,
        "organizations_supplement": set of names,
        "items_new": set of names,
        "items_supplement": set of names,
    }
    返回统计 dict。
    """
    filtered = {
        "characters": [],
        "monsters": [],
        "relations": [],
        "locations": [],
        "organizations": [],
        "items": [],
    }

    # 角色
    for c in extracted.get("characters") or []:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        if (name in selected.get("characters_new", set())
                or name in selected.get("characters_supplement", set())):
            filtered["characters"].append(c)

    for m in extracted.get("monsters") or []:
        if not isinstance(m, dict):
            continue
        name = (m.get("name") or "").strip()
        if not name:
            continue
        if (name in selected.get("monsters_new", set())
                or name in selected.get("monsters_supplement", set())):
            filtered["monsters"].append(m)

    # 关系
    for r in extracted.get("relations") or []:
        if not isinstance(r, dict):
            continue
        key = (
            (r.get("from") or "").strip(),
            (r.get("to") or "").strip(),
            (r.get("type") or "").strip() or "关系",
        )
        if key in selected.get("relations_new", set()):
            filtered["relations"].append(r)

    # 地点
    for l in extracted.get("locations") or []:
        if not isinstance(l, dict):
            continue
        name = (l.get("name") or "").strip()
        if not name:
            continue
        if (name in selected.get("locations_new", set())
                or name in selected.get("locations_supplement", set())):
            filtered["locations"].append(l)

    # 组织
    for o in extracted.get("organizations") or []:
        if not isinstance(o, dict):
            continue
        name = (o.get("name") or "").strip()
        if not name:
            continue
        if (name in selected.get("organizations_new", set())
                or name in selected.get("organizations_supplement", set())):
            filtered["organizations"].append(o)

    # 物品
    for i in extracted.get("items") or []:
        if not isinstance(i, dict):
            continue
        name = (i.get("name") or "").strip()
        if not name:
            continue
        if (name in selected.get("items_new", set())
                or name in selected.get("items_supplement", set())):
            filtered["items"].append(i)

    from .character_extractor import merge_extracted_into_project
    return merge_extracted_into_project(project, filtered)


# ============================================================
# 差异摘要
# ============================================================

def summarize_diff(diff):
    """返回一行摘要文本，用于状态栏或提示"""
    parts = []
    for key, label in [
        ("characters", "角色"),
        ("monsters", "怪物"),
        ("relations", "关系"),
        ("locations", "地点"),
        ("organizations", "组织"),
        ("items", "物品"),
    ]:
        d = diff.get(key, {})
        n = len(d.get("new") or [])
        s = len(d.get("supplement") or [])
        if n or s:
            parts.append(f"{label} 新增{n} / 补充{s}")
    return "；".join(parts) if parts else "无差异"