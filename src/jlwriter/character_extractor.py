"""
档案提取：从章节中提取角色、关系、地点、组织、物品
"""
import json
from .models import (
    CharacterProfile,
    Location,
    Organization,
    Item,
)

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


# ============================================================
# Prompt 构建
# ============================================================

def build_archive_extraction_prompt(vol_idx, ch_idx, vol, ch,
                                    existing_characters=None,
                                    existing_monsters=None,
                                    existing_locations=None,
                                    existing_organizations=None,
                                    existing_items=None,
                                    existing_relations_text=""):
    """
    构建统一的档案提取 prompt。
    existing_* 只应传入"当前章节中已出现过"的实体，避免 token 浪费。
    """
    char_text = _format_existing_characters(existing_characters or [])
    monster_text = _format_existing_monsters(existing_monsters or [])
    loc_text = _format_existing_locations(existing_locations or [])
    org_text = _format_existing_organizations(existing_organizations or [])
    item_text = _format_existing_items(existing_items or [])
    content = (ch.content or "").strip() or "（本章暂无正文内容）"

    prompt = f"""你是专业的小说设定档案管理员。请从下面这一章的正文中，
提取本章出现的角色、地点、物品、组织，以及角色关系。

【已有角色档案】（仅列出本章可能涉及的已有角色）
{char_text}

【已有怪物档案】（仅列出本章可能涉及的已有怪物
{monster_text}

【已有地点档案】（仅列出本章可能涉及的已有地点）
{loc_text}

【已有组织档案】（仅列出本章可能涉及的已有组织）
{org_text}

【已有物品档案】（仅列出本章可能涉及的已有物品）
{item_text}

【已有关系】（仅列出上述已有角色之间的既有关系）
{existing_relations_text or "（暂无已记录关系）"}

【当前章节】
第{vol_idx + 1}卷《{vol.title}》 - 第{ch_idx + 1}章《{ch.title}》
正文：
{content}

【提取要求】
1. 只提取【当前章节】正文中明确出现或间接体现的实体，不得编造
2. 已有实体：只补充本章新出现、之前缺失的信息；已有内容不要重复描述
3. 新实体：完整提取，字段未提及则为空字符串或空数组
4. 别名：同一角色如有不同称呼，填入 aliases
5. 状态字段（age / power_level / emotion / health / status_notes）：
- 这是角色的「最新状态」，每章提取时应以本章正文为准，覆盖旧值\n"
- 若本章未提及某字段，返回空字符串（表示状态未变，不应覆盖旧值）\n
- 若本章明确显示状态变化（如受伤、突破、情绪转折），请输出新值\n"
- 已死亡角色应输出 health=已死亡
5. 时间线：一句话概括角色在本章经历的关键事件；死亡、重伤、失踪、退场必须记录，【100字以内】；若某角色未直接登场但有间接的习惯/设定描述，也应做记录；
6. 关系：
-【关系类型可以包含多重，如：朋友/欺诈、上司/恋人、父子/知己/恋人】
- 支持跨实体类型：角色↔角色、角色→组织、角色→地点、角色↔物品、组织↔组织、组织→地点、地点→地点
   - from 和 to 使用 "类型:名称" 格式，类型可为 character / location / organization / item
   - 只输出本章明确体现的关系，已在【已有关系】中的不要重复
   - 常见关系类型参考：
     角色↔角色：只能取自以下字段：亲人（如夫妻父母子女哥姐弟妹等，详细区分）、敌人、仇人、死敌、兄弟、知己、好友、朋友、导师、恋人、上司、下属、信徒、恩人、合作、利用
     角色→组织：所属/领导/叛出
     角色→地点：常驻/出生于/前往
     角色↔物品：拥有/使用/炼制/遗失
     组织↔组织：敌对/联盟/中立
     组织→地点：位于/辖区
     地点→地点：隶属于/通往
7. 组织成员：只列本章出现或提及的成员
8. 怪物：名称、别名、外形、行为与能力、纲目（可选）,只提取本章出现的怪物
9. 若本章未出现某类实体，对应字段返回空数组

【输出严格 JSON 对象】（不要 markdown，不要额外说明）：
{{
  "characters": [
    {{
      "name": "角色名",
      "aliases": ["别名"],
      "appearance": "外貌，未提及为空字符串",
      "personality": "性格，未提及为空字符串",
      "habits": "语言习惯和习惯性动作，未提及为空字符串",
      "age": "年龄，未提及为空字符串",
      "power_level": "力量等级，未提及为空字符串",
      "emotion": "当前情绪（对某人某事某物的感受），未提及为空字符串",
      "health": "健康状况（健康/受伤/中毒/昏迷/死亡等），未提及为空字符串",
      "status_notes": "其他状态信息（所在地、当前目标、随身物品等），30字以内,未提及为空字符串",
      "timeline_events": ["第{ch_idx + 1}章：事件描述"]
    }}
  ],
  "relations": [
  {{
    "from": "character:角色A",
    "to": "character:角色B",
    "type": "师徒",
    "description": "关系说明",
    "chapter": {ch_idx + 1}
  }},
  {{
    "from": "character:角色A",
    "to": "organization:青云宗",
    "type": "所属",
    "description": "入门弟子",
    "chapter": {ch_idx + 1}
  }}
],
  "monsters": [
    {{
      "name": "怪物名",
      "aliases": ["别名"],
      "appearance": "外形描述",
      "behavior_ability": "行为与能力",
      "category": "纲目（如：妖兽-蛇形-黑鳞蛟科），可空字符串"
    }}
  ]
  "locations": [
    {{
      "name": "地点名",
      "level": "大陆|国家|地区|城市|城区|村镇|建筑|秘境|其他",
      "parent": "上级地点名，无则为空字符串",
      "description": "地理、氛围、特色描述"
    }}
  ],
  "organizations": [
    {{
      "name": "组织名",
      "nature": "门派|家族|王国|教团|商会|行政机构|军事机构|公司|统治者|其他",
      "description": "核心理念与特征描述",
      "members": ["成员角色名"],
      "relations": [
        {{"to": "其他组织名", "type": "敌对|联盟|中立", "description": "关系说明"}}
      ]
    }}
  ],
  "items": [
    {{
      "name": "物品名",
      "type": "神器|法宝|道具|武器|装备|丹药|日用|其他",
      "description": "描述",
      "ability": "特殊能力",
      "owner": "归属者（应以最后状态为主，重点关注是否被售出或转交他人）无归属则为空字符串"
    }}
  ]
}}

只输出 JSON 对象。"""
    return prompt


# ============================================================
# 格式化已有档案
# ============================================================

def _format_existing_characters(characters):
    if not characters:
        return "（本章未涉及任何已有角色，如出现角色请作为新角色提取）"
    lines = []
    for c in characters:
        lines.append(f"角色：{c.name}")
        if getattr(c, "aliases", None):
            lines.append(f"  别名：{'、'.join(c.aliases)}")
        lines.append(f"  外貌：{c.appearance or '（暂无）'}")
        lines.append(f"  性格：{c.personality or '（暂无）'}")
        lines.append(f"  习惯：{c.habits or '（暂无）'}")

        # 当前状态
        status_parts = []
        if getattr(c, "age", ""):
            status_parts.append(f"年龄={c.age}")
        if getattr(c, "power_level", ""):
            status_parts.append(f"力量等级={c.power_level}")
        if getattr(c, "emotion", ""):
            status_parts.append(f"情绪={c.emotion}")
        if getattr(c, "health", ""):
            status_parts.append(f"健康={c.health}")
        if getattr(c, "status_notes", ""):
            status_parts.append(f"其他={c.status_notes}")
        if status_parts:
            lines.append(f"  当前状态：{'；'.join(status_parts)}")

        if c.timeline:
            lines.append("  时间线：")
            for ev in c.timeline[-5:]:
                lines.append(f"    - {ev}")
        lines.append("")
    return "\n".join(lines).rstrip()

def _format_existing_monsters(monsters):
    if not monsters:
        return "（本章未涉及任何已有怪物，如出现怪物请作为新怪物提取）"
    lines = []
    for m in monsters:
        lines.append(f"怪物：{m.name}")
        if m.aliases:
            lines.append(f"  别名：{'、'.join(m.aliases)}")
        if m.category:
            lines.append(f"  纲目：{m.category}")
        if m.appearance:
            lines.append(f"  外形：{m.appearance[:120]}")
        if m.behavior_ability:
            lines.append(f"  行为与能力：{m.behavior_ability[:120]}")
        lines.append("")
    return "\n".join(lines).rstrip()

def _format_existing_locations(locations):
    if not locations:
        return "（本章未涉及任何已有地点，如出现地点请作为新地点提取）"
    lines = []
    for l in locations:
        parent = f"（上级：{l.parent}）" if l.parent else ""
        lines.append(f"地点：{l.name}{parent}（{l.level or '未分类'}）")
        if l.description:
            lines.append(f"  描述：{l.description}")
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_existing_organizations(organizations):
    if not organizations:
        return "（本章未涉及任何已有组织，如出现组织请作为新组织提取）"
    lines = []
    for o in organizations:
        lines.append(f"组织：{o.name}（{o.nature or '未分类'}）")
        if o.description:
            lines.append(f"  描述：{o.description}")
        if o.members:
            lines.append(f"  成员：{'、'.join(o.members[:10])}")
        if o.relations:
            for r in o.relations[:5]:
                lines.append(
                    f"  关系：与{r.get('to', '')}"
                    f"（{r.get('type', '')}）{r.get('description', '')}"
                )
        lines.append("")
    return "\n".join(lines).rstrip()


def _format_existing_items(items):
    if not items:
        return "（本章未涉及任何已有物品，如出现物品请作为新物品提取）"
    lines = []
    for i in items:
        lines.append(f"物品：{i.name}（{i.type or '未分类'}）")
        if i.description:
            lines.append(f"  描述：{i.description}")
        if i.ability:
            lines.append(f"  能力：{i.ability}")
        if i.owner:
            lines.append(f"  归属：{i.owner}")
        lines.append("")
    return "\n".join(lines).rstrip()


# ============================================================
# 响应解析
# ============================================================

def parse_archive_response(text):
    """
    解析 AI 返回，返回 dict：
    {
        "characters": [...],
        "relations": [...],
        "locations": [...],
        "organizations": [...],
        "items": [...]
    }
    """
    if not text:
        return _empty_result()

    t = text.strip()
    if t.startswith("```"):
        lines = t.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()

    s = t.find("{")
    e = t.rfind("}")
    if s == -1 or e <= s:
        raise ValueError("未在响应中找到 JSON 对象")

    json_str = t[s:e + 1]

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        if HAS_JSON_REPAIR:
            data = json_repair.loads(json_str)
        else:
            raise

    if not isinstance(data, dict):
        raise ValueError("AI 输出解析后不是 JSON 对象")

    return {
        "characters": data.get("characters") or [],
        "monsters": data.get("monsters") or [],  # 新增
        "relations": data.get("relations") or [],
        "locations": data.get("locations") or [],
        "organizations": data.get("organizations") or [],
        "items": data.get("items") or [],
    }


def _empty_result():
    return {
        "characters": [], "monsters": [], "relations": [],
        "locations": [], "organizations": [], "items": [],
    }


# ============================================================
# 合并到项目
# ============================================================

def merge_extracted_into_project(project, extracted, relations_list=None):
    """
    将提取结果合并进 project。
    - 新接口：merge_extracted_into_project(project, {"characters": [...], ...})
    - 旧接口兼容：merge_extracted_into_project(project, characters_list, relations_list)
    返回统计 dict。
    """
    # 旧接口兼容
    if isinstance(extracted, list) and relations_list is not None:
        extracted = {
            "characters": extracted,
            "relations": relations_list,
        }

    stats = {
        "characters": 0, "monsters": 0, "relations": 0,
        "locations": 0, "organizations": 0, "items": 0,
    }

    # 先合并实体
    _merge_characters(project, extracted.get("characters") or [], stats)
    _merge_monsters(project, extracted.get("monsters") or [], stats)  # 新增
    _merge_locations(project, extracted.get("locations") or [], stats)
    _merge_organizations(project, extracted.get("organizations") or [], stats)
    _merge_items(project, extracted.get("items") or [], stats)

    # 再合并显式关系 + 展开隐式关系
    _merge_relations(project, extracted.get("relations") or [], stats)

    return stats


def _merge_characters(project, characters, stats):
    for item in characters:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        target = next((c for c in project.characters if c.name == name), None)
        if target is None:
            target = CharacterProfile(name=name)
            project.characters.append(target)
            stats["characters"] += 1

        appearance = (item.get("appearance") or "").strip()
        personality = (item.get("personality") or "").strip()
        habits = (item.get("habits") or "").strip()
        if not target.appearance and appearance:
            target.appearance = appearance
        if not target.personality and personality:
            target.personality = personality
        if not target.habits and habits:
            target.habits = habits

        # 状态字段：有值就覆盖（状态是"最新"语义）
        for fld, key in [
            ("age", "age"),
            ("power_level", "power_level"),
            ("emotion", "emotion"),
            ("health", "health"),
            ("status_notes", "status_notes"),
        ]:
            val = (item.get(key) or "").strip()
            if val:
                setattr(target, fld, val)

        for a in item.get("aliases") or []:
            a = str(a).strip()
            if a and a != target.name and a not in target.aliases:
                target.aliases.append(a)

        for ev in item.get("timeline_events") or []:
            ev = str(ev).strip()
            if ev and ev not in target.timeline:
                target.timeline.append(ev)

def _merge_monsters(project, monsters, stats):
    from .models import Monster
    for item in monsters:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        target = next((m for m in project.monsters if m.name == name), None)
        if target is None:
            target = Monster(name=name)
            project.monsters.append(target)
            stats["monsters"] = stats.get("monsters", 0) + 1

        appearance = (item.get("appearance") or "").strip()
        behavior = (item.get("behavior_ability") or "").strip()
        category = (item.get("category") or "").strip()

        if not target.appearance and appearance:
            target.appearance = appearance
        if not target.behavior_ability and behavior:
            target.behavior_ability = behavior
        if not target.category and category:
            target.category = category

        for a in item.get("aliases") or []:
            a = str(a).strip()
            if a and a != target.name and a not in target.aliases:
                target.aliases.append(a)

def _merge_relations(project, relations, stats):
    from .models import normalize_endpoint, format_endpoint

    for rel in relations:
        if not isinstance(rel, dict):
            continue

        # 兼容 AI 可能输出无前缀的旧格式
        a = normalize_endpoint(rel.get("from", ""))
        b = normalize_endpoint(rel.get("to", ""))
        if not a or not b or a == b:
            continue

        typ = (rel.get("type") or "").strip() or "关系"
        desc = (rel.get("description") or "").strip()
        chapter = rel.get("chapter")

        existing = next(
            (r for r in project.relations
             if r.get("from") == a and r.get("to") == b
             and r.get("type") == typ),
            None
        )
        if existing:
            old = (existing.get("description") or "").strip()
            if desc and desc not in old:
                existing["description"] = (
                    f"{old}；{desc}".strip("；") if old else desc
                )
        else:
            project.relations.append({
                "from": a, "to": b, "type": typ,
                "description": desc, "chapter": chapter,
            })
            stats["relations"] += 1

    # 额外：把组织 members / 地点 parent / 物品 owner 也转为关系
    _expand_implicit_relations(project, stats)


def _expand_implicit_relations(project, stats):
    """
    从组织成员、地点上级、物品归属等字段自动补全跨类型关系。
    与 planner 阶段使用一致的规则。
    """
    from .models import format_endpoint

    def _add(from_ep, to_ep, rel_type, desc=""):
        if not from_ep or not to_ep or from_ep == to_ep:
            return
        for r in project.relations:
            if (r.get("from") == from_ep
                    and r.get("to") == to_ep
                    and r.get("type") == rel_type):
                old = (r.get("description") or "").strip()
                if desc and desc not in old:
                    r["description"] = (
                        f"{old}；{desc}".strip("；") if old else desc
                    )
                return
        project.relations.append({
            "from": from_ep, "to": to_ep,
            "type": rel_type, "description": desc, "chapter": None,
        })
        stats["relations"] += 1

    # 组织成员 → 角色所属组织
    for org in project.organizations:
        for m in org.members or []:
            m = str(m).strip()
            if not m:
                continue
            _add(
                format_endpoint("character", m),
                format_endpoint("organization", org.name),
                "所属", "成员",
            )

    # 地点上级 → 地点隶属于
    for loc in project.locations:
        if loc.parent:
            _add(
                format_endpoint("location", loc.name),
                format_endpoint("location", loc.parent),
                "隶属于",
            )

    # 物品归属 → 拥有
    char_names = {c.name for c in project.characters}
    org_names = {o.name for o in project.organizations}
    for item in project.items:
        owner = (item.owner or "").strip()
        if not owner:
            continue
        if owner in char_names:
            _add(
                format_endpoint("character", owner),
                format_endpoint("item", item.name),
                "拥有",
            )
        elif owner in org_names:
            _add(
                format_endpoint("organization", owner),
                format_endpoint("item", item.name),
                "拥有",
            )


def _merge_locations(project, locations, stats):
    for item in locations:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        target = next((l for l in project.locations if l.name == name), None)
        if target is None:
            target = Location(name=name)
            project.locations.append(target)
            stats["locations"] += 1

        level = (item.get("level") or "").strip()
        parent = (item.get("parent") or "").strip()
        desc = (item.get("description") or "").strip()
        if not target.level and level:
            target.level = level
        if not target.parent and parent:
            target.parent = parent
        if not target.description and desc:
            target.description = desc


def _merge_organizations(project, organizations, stats):
    for item in organizations:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        target = next((o for o in project.organizations if o.name == name), None)
        if target is None:
            target = Organization(name=name)
            project.organizations.append(target)
            stats["organizations"] += 1

        nature = (item.get("nature") or "").strip()
        desc = (item.get("description") or "").strip()
        if not target.nature and nature:
            target.nature = nature
        if not target.description and desc:
            target.description = desc

        for m in item.get("members") or []:
            m = str(m).strip()
            if m and m not in target.members:
                target.members.append(m)

        for rel in item.get("relations") or []:
            if not isinstance(rel, dict):
                continue
            to = (rel.get("to") or "").strip()
            typ = (rel.get("type") or "").strip()
            rdesc = (rel.get("description") or "").strip()
            if not to:
                continue
            dup = next(
                (r for r in target.relations
                 if r.get("to") == to and r.get("type") == typ),
                None
            )
            if dup:
                old = dup.get("description", "")
                if rdesc and rdesc not in old:
                    dup["description"] = (
                        f"{old}；{rdesc}".strip("；") if old else rdesc
                    )
            else:
                target.relations.append({
                    "to": to, "type": typ, "description": rdesc,
                })


def _merge_items(project, items, stats):
    for item in items:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or "").strip()
        if not name:
            continue

        target = next((i for i in project.items if i.name == name), None)
        if target is None:
            target = Item(name=name)
            project.items.append(target)
            stats["items"] += 1

        typ = (item.get("type") or "").strip()
        desc = (item.get("description") or "").strip()
        ability = (item.get("ability") or "").strip()
        owner = (item.get("owner") or "").strip()
        if not target.type and typ:
            target.type = typ
        if not target.description and desc:
            target.description = desc
        if not target.ability and ability:
            target.ability = ability
        if not target.owner and owner:
            target.owner = owner