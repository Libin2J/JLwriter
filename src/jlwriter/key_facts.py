"""
关键事实注册表：从各阶段提取跨阶段一致性依赖的锚点
"""


# 每个阶段需要提取的事实字段
KEY_FACT_EXTRACTORS = {
    "premise": lambda p: {
        "core_conflict": p.get("premise", ""),
    },
    "background": lambda p: {
        "world_name": _extract_first_line(p.get("story_background", "")),
        "era": _match_kw(p.get("story_background", ""),
                         ["古代", "现代", "未来", "架空", "仙侠", "玄幻"]),
        "key_events": _extract_numbered_list(p.get("story_background", ""), 8),
    },
    "power_system": lambda p: {
        "system_name": _extract_first_line(p.get("power_system", "")),
        "levels": _extract_numbered_list(p.get("power_system", ""), 10),
    },
    "outline": lambda p: {
        "volumes": _extract_volumes(p.get("outline", "")),
    },
    "characters": lambda p: {
        "characters": [
            {
                "name": c.get("name", ""),
                "aliases": c.get("aliases", []),
                "identity": c.get("identity", "")[:80],
                "role": c.get("role", ""),
            }
            for c in (p.get("characters") or [])
        ],
    },
    "organizations": lambda p: {
        "organizations": [
            {
                "name": o.get("name", ""),
                "nature": o.get("nature", ""),
                "members": o.get("members", []),
            }
            for o in (p.get("organizations") or [])
        ],
    },
    "locations": lambda p: {
        "locations": [
            {
                "name": l.get("name", ""),
                "level": l.get("level", ""),
                "parent": l.get("parent", ""),
            }
            for l in (p.get("locations") or [])
        ],
    },
    "items": lambda p: {
        "items": [
            {
                "name": i.get("name", ""),
                "type": i.get("type", ""),
                "owner": i.get("owner", ""),
            }
            for i in (p.get("items") or [])
        ],
    },
    "monsters": lambda p: {
        "monsters": [
            {
                "name": m.get("name", ""),
                "category": m.get("category", ""),
                "aliases": m.get("aliases", [])[:3],
            }
            for m in (p.get("monsters") or [])
        ],
    },
}

# 每个阶段的关键事实输出结构（用于构建 prompt，描述字段含义与示例）
KEY_FACT_SCHEMAS = {
    "premise": {
        "core_conflict": "核心矛盾一句话（40字以内）",
    },
    "background": {
        "world_name": "世界/大陆名",
        "era": "时代背景（如：古代/现代/未来/架空/仙侠/玄幻）",
        "key_events": ["关键历史事件（每条 20-40 字）"],
    },
    "power_system": {
        "system_name": "体系名称",
        "levels": ["等级名（从低到高，每条 20-30 字）"],
    },
    "outline": {
        "volumes": [
            {
                "volume": "卷名（含'第X卷'）",
            }
        ],
    },
    "characters": {
        "characters": [
            {
                "name": "正式名",
                "aliases": ["别名"],
                "identity": "身份（15字以内）",
                "role": "主角/配角/反派/导师/其他",
            }
        ],
    },
    "organizations": {
        "organizations": [
            {
                "name": "势力名",
                "nature": "宗教、家族、王国、公司、社团、行政机构、军事机构、统治者等",
                "members": ["重要成员名"],
            }
        ],
    },
    "locations": {
        "locations": [
            {
                "name": "地名",
                "level": "大陆 / 国家 / 城市 / 城区 / 建筑 / 秘境",
                "parent": "上级地点名（若提及，否则空字符串）",
            }
        ],
    },
    "items": {
        "items": [
            {
                "name": "物品名",
                "type": "神器/法宝/道具/武器等",
                "owner": "归属者（若提及，否则空字符串）",
            }
        ],
    },
    "monsters": {
        "monsters": [
            {
                "name": "怪物名",
                "category": "纲目（可选）",
                "aliases": ["别名"],
            }
        ],
    },
}


def build_key_facts_extraction_prompt(stage_id, stage_label, parsed_content) -> str:
    content_str = stringify_parsed(parsed_content)
    schema = KEY_FACT_SCHEMAS.get(stage_id, {})

    schema_lines = []
    for k, v in schema.items():
        if isinstance(v, list):
            if v and isinstance(v[0], dict):
                schema_lines.append(
                    f'  "{k}": [ {{...}} ]，其中每个元素包含：'
                )
                for ik, iv in v[0].items():
                    if isinstance(iv, list):
                        desc = " / ".join(str(x) for x in iv) if iv else "字符串数组"
                        schema_lines.append(f'    - {ik}: [{desc}]')
                    else:
                        schema_lines.append(f'    - {ik}: {iv}')
            else:
                sample = v[0] if v else "字符串"
                schema_lines.append(f'  "{k}": [ {sample} ]')
        else:
            schema_lines.append(f'  "{k}": "{v}"')

    schema_text = "\n".join(schema_lines)

    parts = []
    parts.append(
        "你是小说设定档案管理员。请从下面这一阶段的内容中，"
        "提取所有跨阶段一致性依赖的关键事实。\n"
    )
    parts.append(f"【{stage_label}】")
    parts.append(content_str)
    parts.append("")
    parts.append(
        "【提取原则】\n"
        "1. 只提取后续阶段需要引用的锚点：实体名、规则名、身份、层级、关系\n"
        "2. 忽略文风、修辞、情感描写\n"
        "3. 严格保留实体名与人名的原样，不要改写、不要编造\n"
        "4. 若某实体有别名，一并列出\n"
        "5. 若某字段在本阶段未提及，返回空字符串或空数组\n"
        "6. 不要无中生有，只提取原文明确存在的信息\n"
    )
    parts.append("")
    parts.append("【输出结构】")
    parts.append("{\n"
                 '  "_thought": "简要说明，50字以内",\n'
                 '  "key_facts": {\n'
                 f"{schema_text}\n"
                 "  }\n"
                 "}")
    parts.append("")
    parts.append("【输出格式】")
    parts.append("只输出 JSON，不要 markdown。")

    return "\n".join(parts)


def parse_key_facts_response(text: str) -> dict:
    from .planner_agent import parse_stage_response
    data = parse_stage_response(text)
    if not isinstance(data, dict):
        raise ValueError("提炼结果不是 JSON 对象")
    return data.get("key_facts", {}) or {}

def extract_key_facts(stage_id: str, parsed: dict) -> dict:
    """从某阶段的生成结果提取关键事实"""
    extractor = KEY_FACT_EXTRACTORS.get(stage_id)
    if not extractor:
        return {}
    try:
        return extractor(parsed)
    except Exception:
        return {}



def format_key_facts_for_prompt(registry: dict) -> str:
    """把关键事实清单转为 prompt 文本"""
    if not registry:
        return "（无前序锚点）"

    parts = []
    order = ["premise", "background", "power_system", "outline",
             "characters", "organizations", "locations", "items", "monsters"]
    labels = {
        "premise": "核心矛盾",
        "background": "故事背景",
        "power_system": "力量体系",
        "outline": "故事总纲",
        "characters": "关键人物",
        "organizations": "主要势力",
        "locations": "地图与地点",
        "items": "重要物品",
        "monsters": "怪物",
    }

    for sid in order:
        if sid not in registry:
            continue
        parts.append(f"【{labels.get(sid, sid)}】")
        facts = registry[sid]
        for k, v in facts.items():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        line = "  - " + "；".join(
                            f"{ik}: {iv}" for ik, iv in item.items() if iv
                        )
                        parts.append(line)
                    else:
                        parts.append(f"  - {item}")
            else:
                parts.append(f"  {k}: {v}")
        parts.append("")

    return "\n".join(parts)


# ---------- 辅助函数 ----------

def _extract_first_line(text: str) -> str:
    for line in (text or "").splitlines():
        line = line.strip()
        if line:
            return line[:120]
    return ""


def _match_kw(text: str, keywords: list) -> str:
    text = text or ""
    for kw in keywords:
        if kw in text:
            return kw
    return ""


def _extract_numbered_list(text: str, max_items: int = 8) -> list:
    """从文本中提取形如"1. xxx"、"一、xxx"、"【xxx】"的条目"""
    import re
    if not text:
        return []
    results = []
    # 匹配 "1. 内容" / "1、内容" / "一、内容" / "【内容】"
    patterns = [
        r'^\s*\d+[\.、]\s*(.+)$',
        r'^\s*[一二三四五六七八九十]+[\.、]\s*(.+)$',
        r'^\s*【(.+?)】',
    ]
    for line in text.splitlines():
        for pat in patterns:
            m = re.match(pat, line)
            if m:
                item = m.group(1).strip()
                if item and item not in results:
                    results.append(item[:100])
                break
        if len(results) >= max_items:
            break
    return results


def _extract_volumes(outline: str) -> list:
    """从故事总纲提取卷名与主题"""
    import re
    if not outline:
        return []
    results = []
    for line in outline.splitlines():
        m = re.match(r'^\s*第\s*[一二三四五六七八九十\d]+\s*卷[：:\s]*(.+)$', line)
        if m:
            title = m.group(1).strip()[:80]
            if title:
                results.append({"volume": title})
    return results[:10]

# ---------- 通用工具 ----------

def stringify_parsed(parsed) -> str:
    """
    把阶段解析结果转为可读文本，用于 prompt 组装。
    - dict：逐字段展开，跳过以 _ 开头的元字段
    - list：逐项展开
    - 其他：直接 str
    """
    if isinstance(parsed, dict):
        lines = []
        for k, v in parsed.items():
            if k.startswith("_"):
                continue
            if isinstance(v, list):
                lines.append(f"{k}:")
                for item in v:
                    if isinstance(item, dict):
                        lines.append("  - " + "; ".join(
                            f"{ik}: {iv}" for ik, iv in item.items() if iv
                        ))
                    else:
                        lines.append(f"  - {item}")
            else:
                lines.append(f"{k}: {v}")
        return "\n".join(lines)
    return str(parsed)