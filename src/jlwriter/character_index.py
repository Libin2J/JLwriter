"""
角色-章节索引与子图筛选：初步 GraphRAG 支撑
"""
from typing import Dict, Set, Tuple
from .models import parse_endpoint

def _mentioned(text: str, profile) -> bool:
    """判断角色（或其别名）是否在文本中出现"""
    if not text:
        return False
    names = [profile.name] + list(getattr(profile, "aliases", []) or [])
    for n in names:
        if not n:
            continue
        n = n.strip()
        if len(n) < 2:      # 单字名容易误匹配，跳过
            continue
        if n in text:
            return True
    return False


def build_chapter_character_index(project) -> Dict[Tuple[int, int], Set[str]]:
    """构建 {(vol_idx, ch_idx): {角色名, ...}} 索引"""
    index: Dict[Tuple[int, int], Set[str]] = {}
    for vi, vol in enumerate(project.volumes):
        for ci, ch in enumerate(vol.chapters):
            text = f"{ch.content or ''}\n{ch.summary or ''}"
            names: Set[str] = set()
            for profile in project.characters:
                if _mentioned(text, profile):
                    names.add(profile.name)
            index[(vi, ci)] = names
    return index


def _flat_order(project):
    order = []
    for vi, vol in enumerate(project.volumes):
        for ci in range(len(vol.chapters)):
            order.append((vi, ci))
    return order


def select_characters_for_context(project, vol_idx: int, ch_idx: int,
                                  lookback: int = 3, hops: int = 1) -> Set[str]:
    """
    为当前章节筛选相关角色：
      - 当前章节中出现的角色
      - 前 lookback 章中出现的角色
      - 上述角色沿 relations 做 hops 跳扩展
    """
    index = build_chapter_character_index(project)
    selected: Set[str] = set(index.get((vol_idx, ch_idx), set()))

    order = _flat_order(project)
    try:
        pos = order.index((vol_idx, ch_idx))
    except ValueError:
        pos = None

    if pos is not None:
        start = max(0, pos - lookback)
        for i in range(start, pos):
            selected |= index.get(order[i], set())

    # 关系扩展
    if hops > 0 and project.relations:
        expanded = set(selected)
        for _ in range(hops):
            new_added: Set[str] = set()
            for rel in project.relations:
                a = (rel.get("from") or "").strip()
                b = (rel.get("to") or "").strip()
                if not a or not b:
                    continue
                if a in expanded and b not in expanded:
                    new_added.add(b)
                if b in expanded and a not in expanded:
                    new_added.add(a)
            if not new_added:
                break
            expanded |= new_added
        selected = expanded

    return selected


def format_characters_for_prompt(project, names: Set[str]) -> str:
    """将筛选后的角色档案 + 关系边格式化为 prompt 文本"""
    if not names:
        return "（本章暂无相关角色档案）"
    profiles = [c for c in project.characters if c.name in names]
    if not profiles:
        return "（本章暂无相关角色档案）"

    parts = []
    for c in profiles:
        parts.append(f"角色：{c.name}")
        if getattr(c, "aliases", None):
            parts.append(f"  别名：{'、'.join(c.aliases)}")
        if c.appearance:
            parts.append(f"  外貌：{c.appearance}")
        if c.personality:
            parts.append(f"  性格：{c.personality}")
        if c.habits:
            parts.append(f"  习惯：{c.habits}")
        if c.timeline:
            parts.append("  时间线：")
            for ev in c.timeline:
                parts.append(f"    - {ev}")
        if c.is_dead():
            parts.append("  【注意：该角色已死亡】")

        rel_lines = []
        for rel in project.relations:
            a = (rel.get("from") or "").strip()
            b = (rel.get("to") or "").strip()
            typ = (rel.get("type") or "关系").strip()
            desc = (rel.get("description") or "").strip()
            ch = rel.get("chapter")
            suffix = f"（第{ch}章）" if ch else ""
            if a == c.name and b in names:
                rel_lines.append(f"    - {c.name} → {b}：{typ} {desc}{suffix}")
            elif b == c.name and a in names:
                rel_lines.append(f"    - {a} → {c.name}：{typ} {desc}{suffix}")
        if rel_lines:
            parts.append("  关系：")
            parts.extend(rel_lines)

        parts.append("")
    return "\n".join(parts).rstrip()


def get_characters_mentioned_in_chapter(project, vol_idx: int, ch_idx: int):
    """
    用于章节人物画像提取
    返回当前章节中出现过的已有角色档案列表
    匹配依据：角色 name 或 aliases 是否出现在章节正文或摘要中。
    """
    if not (0 <= vol_idx < len(project.volumes)):
        return []
    vol = project.volumes[vol_idx]
    if not (0 <= ch_idx < len(vol.chapters)):
        return []
    ch = vol.chapters[ch_idx]
    text = f"{ch.content or ''}\n{ch.summary or ''}"

    mentioned = []
    for profile in project.characters:
        if _mentioned(text, profile):
            mentioned.append(profile)
    return mentioned


def filter_relations_for_names(project, names: set) -> str:
    """
    保留至少一端命中 names 的关系（支持跨类型端点）。
    names 只包含角色名，端点使用 character:xxx 或 organization:xxx 等格式。
    """
    if not project.relations or not names:
        return "（暂无已记录关系）"

    from .models import parse_endpoint

    lines = []
    for rel in project.relations:
        a = (rel.get("from") or "").strip()
        b = (rel.get("to") or "").strip()
        if not a or not b:
            continue
        _, a_name = parse_endpoint(a)
        _, b_name = parse_endpoint(b)
        # 至少一端是相关角色
        if a_name not in names and b_name not in names:
            continue
        typ = (rel.get("type") or "关系").strip()
        desc = (rel.get("description") or "").strip()
        line = f"{a} → {b}（{typ}）"
        if desc:
            line += f" {desc}"
        if line not in lines:
            lines.append(line)

    return "\n".join(lines) if lines else "（暂无已记录关系）"

# ============================================================
# 通用实体筛选：地点 / 组织 / 物品
# ============================================================

def _get_chapter_text(project, vol_idx, ch_idx):
    """取某章的正文 + 摘要 + 规划文本，用于实体匹配"""
    if not (0 <= vol_idx < len(project.volumes)):
        return ""
    vol = project.volumes[vol_idx]
    if not (0 <= ch_idx < len(vol.chapters)):
        return ""
    ch = vol.chapters[ch_idx]
    parts = [ch.content or "", ch.summary or ""]
    plan = getattr(ch, "plan", None)
    if plan:
        parts.append(plan.to_prompt_text())
    return "\n".join(parts)


def _mentioned_entity(text, name, aliases=None):
    """通用实体匹配：name 或 aliases 任一在 text 中出现即命中"""
    if not text or not name:
        return False
    candidates = [name] + list(aliases or [])
    for n in candidates:
        if not n:
            continue
        n = str(n).strip()
        if len(n) < 2:
            continue
        if n in text:
            return True
    return False

def get_monsters_mentioned_in_chapter(project, vol_idx, ch_idx):
    """返回当前章节中出现过的已有怪物档案列表"""
    text = _get_chapter_text(project, vol_idx, ch_idx)
    if not text:
        return []
    return [m for m in project.monsters
            if _mentioned_entity(text, m.name, m.aliases)]


def get_locations_mentioned_in_chapter(project, vol_idx, ch_idx):
    """返回当前章节中出现过的已有地点档案列表"""
    text = _get_chapter_text(project, vol_idx, ch_idx)
    if not text:
        return []
    return [loc for loc in project.locations
            if _mentioned_entity(text, loc.name)]


def get_organizations_mentioned_in_chapter(project, vol_idx, ch_idx):
    """返回当前章节中出现过的已有组织档案列表"""
    text = _get_chapter_text(project, vol_idx, ch_idx)
    if not text:
        return []
    return [org for org in project.organizations
            if _mentioned_entity(text, org.name)]


def get_items_mentioned_in_chapter(project, vol_idx, ch_idx):
    """返回当前章节中出现过的已有物品档案列表"""
    text = _get_chapter_text(project, vol_idx, ch_idx)
    if not text:
        return []
    return [item for item in project.items
            if _mentioned_entity(text, item.name)]


def load_entities_by_names(project, required_entities):
    """
    按细纲给出的实体清单加载完整档案。
    返回 (profiles_dict, missing_names)
    """
    profiles = {
        "characters": [],
        "locations": [],
        "items": [],
        "organizations": [],
        "monsters": [],
    }
    missing = {
        "characters": [], "locations": [],
        "items": [], "organizations": [], "monsters": [],
    }

    char_lookup = {c.name: c for c in project.characters}
    loc_lookup = {l.name: l for l in project.locations}
    item_lookup = {i.name: i for i in project.items}
    org_lookup = {o.name: o for o in project.organizations}
    monster_lookup = {m.name: m for m in project.monsters}

    for name in required_entities.get("characters", []):
        if name in char_lookup:
            profiles["characters"].append(char_lookup[name])
        else:
            missing["characters"].append(name)

    for name in required_entities.get("monsters", []):
        if name in monster_lookup:
            profiles["monsters"].append(monster_lookup[name])
        else:
            missing["monsters"].append(name)

    for name in required_entities.get("locations", []):
        if name in loc_lookup:
            profiles["locations"].append(loc_lookup[name])
        else:
            missing["locations"].append(name)

    for name in required_entities.get("items", []):
        if name in item_lookup:
            profiles["items"].append(item_lookup[name])
        else:
            missing["items"].append(name)

    for name in required_entities.get("organizations", []):
        if name in org_lookup:
            profiles["organizations"].append(org_lookup[name])
        else:
            missing["organizations"].append(name)

    return profiles, missing


def format_profiles_for_prompt(project, profiles) -> str:
    """把加载到的实体档案格式化为 prompt 文本"""
    parts = []

    if profiles["characters"]:
        parts.append("▸ 相关角色")
        for c in profiles["characters"]:
            parts.append(f"【{c.name}】")
            if c.aliases:
                parts.append(f"  别名：{'、'.join(c.aliases)}")
            if c.appearance:
                parts.append(f"  外貌：{c.appearance}")
            if c.personality:
                parts.append(f"  性格：{c.personality}")
            if c.habits:
                parts.append(f"  习惯：{c.habits}")

            # 新增：当前状态
            status_text = ""
            if hasattr(c, "format_status_for_prompt"):
                status_text = c.format_status_for_prompt()
            if status_text:
                parts.append(f"  当前状态：{status_text}")

            if c.is_dead():
                parts.append("  【注意：该角色已死亡】")
            # 与本章其他角色的关系
            name_set = {x.name for x in profiles["characters"]}
            for rel in project.relations:
                a = rel.get("from", "")
                b = rel.get("to", "")
                from .models import parse_endpoint
                _, a_name = parse_endpoint(a) if ":" in a else ("", a)
                _, b_name = parse_endpoint(b) if ":" in b else ("", b)
                if c.name in (a_name, b_name):
                    other = b_name if c.name == a_name else a_name
                    if other in name_set:
                        parts.append(
                            f"  关系：与{other}（{rel.get('type', '')}）"
                            f"{rel.get('description', '')}"
                        )
            parts.append("")

    if profiles.get("monsters"):
        parts.append("▸ 相关怪物")
        for m in profiles["monsters"]:
            parts.append(f"【{m.name}】")
            if m.aliases:
                parts.append(f"  别名：{'、'.join(m.aliases)}")
            if m.category:
                parts.append(f"  纲目：{m.category}")
            if m.appearance:
                parts.append(f"  外形：{m.appearance}")
            if m.behavior_ability:
                parts.append(f"  行为与能力：{m.behavior_ability}")
            parts.append("")

    if profiles["organizations"]:
        parts.append("▸ 相关组织")
        for o in profiles["organizations"]:
            parts.append(f"【{o.name}】{o.nature}")
            if o.description:
                parts.append(f"  {o.description}")
            if o.members:
                parts.append(f"  成员：{'、'.join(o.members)}")
            parts.append("")

    if profiles["locations"]:
        parts.append("▸ 相关地点")
        for l in profiles["locations"]:
            parent = f"（上级：{l.parent}）" if l.parent else ""
            parts.append(f"【{l.name}】{parent}{l.level}")
            if l.description:
                parts.append(f"  {l.description}")
            parts.append("")

    if profiles["items"]:
        parts.append("▸ 相关物品")
        for i in profiles["items"]:
            owner = f"｜归属：{i.owner}" if i.owner else ""
            parts.append(f"【{i.name}】{i.type}")
            if i.description:
                parts.append(f"  {i.description}")
            if i.ability:
                parts.append(f"  能力：{i.ability}{owner}")
            parts.append("")

    return "\n".join(parts).rstrip()