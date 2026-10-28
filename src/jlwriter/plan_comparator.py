"""
规划差异对比：给定章节规划与实际正文，让 extractor agent 输出结构化偏离报告
"""
from .models import PlanDeviationReport, DimensionDeviation
from .planner_agent import parse_stage_response


DIMENSION_LABELS = {
    "goal": "章节目标",
    "characters": "出场人物",
    "key_events": "关键事件",
    "foreshadowing": "伏笔",
    "ending_hook": "结尾钩子",
    "detailed_outline": "细纲节拍",     # 新增
}

STATUS_LABELS = {
    "achieved": "达成",
    "partial": "部分达成",
    "deviated": "偏离",
    "missing": "未涉及",
    "unknown": "未知",
}

STATUS_COLORS = {
    "achieved": "#4CAF50",
    "partial": "#FF9800",
    "deviated": "#F44336",
    "missing": "#9E9E9E",
    "unknown": "#9E9E9E",
}


def build_deviation_prompt(project, vol_idx, ch_idx, chapter,
                           max_content_chars=12000) -> str:
    """
    构建偏离校验 prompt：除本章规划与正文外，额外传入
    - L1 世界规则（硬约束，避免误判世界观层面的合理描写）
    - 前序章节大纲（避免误判前情已设定的内容）
    - 相关实体档案（避免误判角色/地点/物品的合理出现）
    """
    plan = getattr(chapter, "plan", None)
    if not plan:
        return ""

    plan_text = plan.to_prompt_text()

    content = (chapter.content or "").strip()
    if len(content) > max_content_chars:
        content = (
            content[:max_content_chars]
            + f"\n……（已截断，原文字数 {len(chapter.content)}）"
        )

    # 前序上下文
    world_rules = _collect_world_rules(project)
    prev_outlines = _collect_preceding_outlines(project, vol_idx, ch_idx, count=5)
    relevant_entities = _collect_relevant_entities(project, vol_idx, ch_idx)

    # 分段拼接，避免大段 f-string 花括号问题
    parts = []

    parts.append(
        "你是小说编辑助手。请对比【章节规划】与【实际正文】，输出结构化的偏离报告。\n"
    )
    parts.append(
        "【重要判定原则】\n"
        "1. 只有与【章节规划】直接冲突的内容，才算「偏离」\n"
        "2. 下列内容不算偏离（属于合理存在，不得要求删除）：\n"
        "   a. 规划未提及，但与前序章节大纲一致的延续性内容\n"
        "   b. 规划未提及，但与 L1 世界规则一致的世界观细节\n"
        "   b. 规划未提及，但属于相关实体档案中的既有设定\n"
        "   c. 规划未提及，属于合理的过渡描写、氛围渲染、日常互动\n"
        "   d. 规划未提及，属于对已有能力的自然使用（如既有的功法、物品）\n"
        "   i, 规划内提及，正文未直接描写的地点，但能够被正文内描写地点的上级地点关联，不算偏离，如：规划要求明烛基地、影环，正文仅提及影环，而影环<-明烛基地，此时不算偏离\n"
        "3. 只有下列情况才算真正的偏离：\n"
        "   a. 违反规划中的【本章目标】或【关键事件】\n"
        "   b. 提前完成规划之外、属于后续章节的情节\n"
        "   c. 违反 L1 世界规则（如力量体系、背景设定）\n"
        "   d. 与前序章节大纲矛盾（如前序已死角色在本章活跃）\n"
        "   e. 结尾未落在规划的【结尾钩子】上\n"
        "   f. 出现规划明确要求「不出现」的角色或事件\n"
        "   g. 正文跳过了细纲中的某个场景节拍\n"
        "   h. 正文的场景顺序与细纲明显不符（如前两节拍颠倒）\n"
    )
    parts.append("")

    if world_rules:
        parts.append("【L1 世界规则（硬约束）】")
        parts.append(world_rules)
        parts.append("")

    if prev_outlines:
        parts.append("【前序章节大纲（已发生，作为判定基准）】")
        parts.append(prev_outlines)
        parts.append("")

    if relevant_entities:
        parts.append("【本章相关实体档案（既有设定）】")
        parts.append(relevant_entities)
        parts.append("")

    parts.append("【章节规划】")
    parts.append(plan_text)
    parts.append("")

    # 过渡定位（不在 to_prompt_text 中）
    if plan.transition_notes:
        parts.append(f"【本章过渡定位】{plan.transition_notes}")
        parts.append("")

    # 细纲要求的实体清单（不在 to_prompt_text 中）
    re_dict = plan.required_entities or {}
    entity_lines = []
    for k, label in [
        ("characters", "角色"),
        ("locations", "地点"),
        ("items", "物品"),
        ("organizations", "组织"),
    ]:
        names = re_dict.get(k) or []
        if names:
            entity_lines.append(f"{label}：{'、'.join(names)}")
    if entity_lines:
        parts.append("【细纲要求的实体清单（本章应出现）】")
        parts.extend(entity_lines)
        parts.append("")

    parts.append("【实际正文】")
    parts.append(content)
    parts.append("")

    parts.append(
        "【对比要求】\n"
        "逐个维度对比：\n"
        "- goal：正文是否完成了规划中的叙事目标\n"
        "- characters：规划的出场人物是否都出现？是否有规划外人物？"
        "（若为前序已建立角色且合理出现，不算偏离）\n"
        "- key_events：每个规划事件是否发生？是否有新事件？"
        "（新事件若属于合理过渡，不算偏离）\n"
        "- foreshadowing：规划的伏笔是否埋下？\n"
        "- ending_hook：正文结尾是否落在规划的钩子上\n"
        "- detailed_outline（若规划中存在细纲，必须校验此项）：\n"
        "    · 正文是否按细纲的每个场景节拍依次推进？\n"
        "    · 是否有节拍被跳过、合并、或顺序打乱？\n"
        "    · 是否有细纲之外的关键节拍插入？\n"
        "    · 若细纲的某节拍在正文中完全缺失，status 记为 missing\n"
    )
    parts.append("")

    parts.append(
        "status 只能取：\n"
        "- achieved：完全达成\n"
        "- partial：部分达成\n"
        "- deviated：与规划有明显偏离\n"
        "- missing：未涉及\n"
    )
    parts.append("")

    parts.append(
        "计算 overall_score（0-100）时，只对「真正的偏离」扣分：\n"
        "- 90+：几乎完全按规划推进，且未违反世界规则\n"
        "- 75-89：主要维度达成，细节有出入\n"
        "- 60-74：核心维度基本达成，但有明显偏离\n"
        "- 40-59：多个维度偏离\n"
        "- <40：严重偏离规划或违反世界规则\n"
    )
    parts.append("")

    parts.append(
        "【输出格式】\n"
        "只输出 JSON，不要 markdown 标记或额外说明：\n"
        "{\n"
        '  "_thought": "简要思考，100字以内",\n'
        '  "overall_score": 0-100,\n'
        '  "summary": "一句话总结",\n'
        '  "dimensions": [\n'
        "    {\n"
        '      "dimension": "goal",\n'
        '      "status": "achieved",\n'
        '      "planned": "规划中的内容摘要",\n'
        '      "actual": "正文实际呈现的摘要",\n'
        '      "comment": "对比说明"\n'
        "    }\n"
        "  ],\n"
        '  "extra_content": ["规划外且不属于合理延续的内容"],\n'
        '  "suggestions": "改进建议"\n'
        "}\n"
    )
    parts.append("")
    parts.append(
        "注意：dimension 字段只能取 goal / characters / key_events / "
        "foreshadowing / ending_hook 之一，且必须覆盖所有规划中出现的维度。\n"
        "extra_content 只列出「真正偏离」的内容，不含前序已设定的合理延续。"
    )

    return "\n".join(parts)


def parse_deviation_response(text: str, chapter_title: str = "") -> PlanDeviationReport:
    """解析 AI 返回的偏离报告"""
    data = parse_stage_response(text)
    if not isinstance(data, dict):
        raise ValueError("AI 输出不是 JSON 对象")

    report = PlanDeviationReport(chapter_title=chapter_title)
    try:
        report.overall_score = int(data.get("overall_score", 0) or 0)
    except (ValueError, TypeError):
        report.overall_score = 0
    report.overall_score = max(0, min(100, report.overall_score))

    report.summary = (data.get("summary") or "").strip()
    report.suggestions = (data.get("suggestions") or "").strip()

    seen_dims = set()
    for d in data.get("dimensions", []) or []:
        if not isinstance(d, dict):
            continue
        dim = (d.get("dimension") or "").strip()
        if not dim or dim in seen_dims:
            continue
        seen_dims.add(dim)
        status = (d.get("status") or "unknown").strip()
        if status not in STATUS_LABELS:
            status = "unknown"
        report.dimensions.append(DimensionDeviation(
            dimension=dim,
            status=status,
            planned=(d.get("planned") or "").strip(),
            actual=(d.get("actual") or "").strip(),
            comment=(d.get("comment") or "").strip(),
        ))

    for e in data.get("extra_content", []) or []:
        e = str(e).strip()
        if e:
            report.extra_content.append(e)

    return report


# ============================================================
# 关系校验
# ============================================================

def build_relation_check_prompt(project, vol_idx, ch_idx, chapter) -> str:
    """
    关系时序校验：检查本章正文中是否出现了"提前建立"的关系。
    """
    # 收集"截至本章之前"应存在的关系
    expected_relations = _collect_expected_relations(project, vol_idx, ch_idx)

    # 收集本章正文中实际出现的角色
    from .character_index import get_characters_mentioned_in_chapter
    mentioned_chars = get_characters_mentioned_in_chapter(
        project, vol_idx, ch_idx
    )
    mentioned_names = [c.name for c in mentioned_chars]

    content = (chapter.content or "").strip()
    if len(content) > 10000:
        content = content[:10000] + f"\n……（已截断，原文字数 {len(chapter.content)}）"

    # 期望关系文本
    if expected_relations:
        exp_lines = []
        for r in expected_relations:
            exp_lines.append(
                f"- {r['from']} → {r['to']}（{r['type']}）"
                f"｜首次出现：第{r.get('chapter', '?')}章"
                f"｜{r.get('description', '')}"
            )
        exp_text = "\n".join(exp_lines)
    else:
        exp_text = "（暂无）"

    # 已有实体清单（供判断关系端点的合法性）
    # entity_lines = []
    # for c in mentioned_chars:
    #     entity_lines.append(f"- 角色：{c.name}")
    # for o in project.organizations:
    #     if o.name and o.name in content:
    #         entity_lines.append(f"- 组织：{o.name}")
    # for l in project.locations:
    #     if l.name and l.name in content:
    #         entity_lines.append(f"- 地点：{l.name}")
    # for i in project.items:
    #     if i.name and i.name in content:
    #         entity_lines.append(f"- 物品：{i.name}")
    # entity_text = "\n".join(entity_lines) if entity_lines else "（无）"

    plan = getattr(chapter, "plan", None)
    re_lines = []
    if plan and plan.required_entities:
        for k, label in [
            ("characters", "角色"),
            ("locations", "地点"),
            ("items", "物品"),
            ("organizations", "组织"),
        ]:
            names = plan.required_entities.get(k) or []
            if names:
                re_lines.append(f"{label}：{'、'.join(names)}")
    entity_check_block = ""
    if re_lines:
        entity_check_block = (
                "【细纲要求的实体（本章应出现）】\n"
                + "\n".join(re_lines) + "\n\n"
        )

    # 在 prompt 的主结构里，把 entity_check_block 插在【本章正文】之前

    prompt = f"""你是小说一致性校验员。请检查下面这一章的正文中，
是否存在"关系时序错误"——即某些关系在本章出现，但按规划它们本应更晚建立。

【截至本章之前的既有关系】（这些关系在本章成立是合理的）
{exp_text}

【本章涉及的角色与实体】
{entity_check_block}

【本章正文】
{content}

【校验维度】
1. **提前建立**：本章出现了某段关系，但该关系在【既有关系】中不存在，
   而按本章规划也不应出现 → 这是提前建立，应指出
2. **关系突变**：既有关系在本章发生了无铺垫的逆转（如师父突然变仇敌），
   且本章规划未提及该转变
3. **不该出现的关系**：本章出现了超越当前剧情进度的关系描述
   （如"十年前就已决裂"但实际决裂尚未发生）
4. **实体清单覆盖**：细纲要求的实体在本章中是否全部出现？
    若某实体规划要求出现但正文完全没有，应报告为 high 严重度问题

【输出严格 JSON】（不要 markdown，不要额外说明）：
{{
  "_thought": "简要判断，80字以内",
  "issues": [
    {{
      "severity": "high|medium|low",
      "from": "角色A",
      "to": "角色B",
      "type": "关系类型",
      "description": "问题描述",
      "suggestion": "修正方向"
    }}
  ],
  "summary": "总体说明"
}}

【重要】
- 若本章没有关系时序问题，issues 返回 []
- description 明确指出"该关系在当前章不成立的原因"
- suggestion 给出修正方向（如"应改写为陌生关系，留待后续章节建立"）"""
    return prompt


def _collect_expected_relations(project, vol_idx, ch_idx):
    """
    收集"截至本章之前"应存在的关系。
    依据：前序章节的规划中是否提及过该关系，或 L0 世界状态中是否记录。
    """
    result = []
    flat = []
    for vi, vol in enumerate(project.volumes):
        for ci, ch in enumerate(vol.chapters):
            flat.append((vi, ci, ch))

    cur_pos = None
    for i, (vi, ci, _) in enumerate(flat):
        if vi == vol_idx and ci == ch_idx:
            cur_pos = i
            break
    if cur_pos is None:
        return []

    # 遍历前序章节的规划，收集已提及的关系
    seen_keys = set()
    for i in range(cur_pos):
        vi, ci, ch = flat[i]
        plan = getattr(ch, "plan", None)
        if not plan:
            continue
        for fs in plan.key_events or []:
            # 简化处理：从关键事件中提取可能的关系建立
            # 更精确的方式依赖 AI，此处只做"已知关系"的粗筛
            pass

    # 直接使用 project.relations 中已存在的关系
    # 但过滤掉"已在本章规划中出现"的关系——因为本章正在建立它们
    cur_plan = getattr(project.volumes[vol_idx].chapters[ch_idx], "plan", None)
    current_relations = set()
    if cur_plan:
        for ev in cur_plan.key_events or []:
            current_relations.add(ev)

    for r in project.relations or []:
        # 只保留已经在前序章节中记录过的关系
        chapter = r.get("chapter")
        if chapter is None:
            continue
        try:
            chapter_int = int(chapter)
        except (TypeError, ValueError):
            continue
        # chapter 是 1-based 章号；只有 < 当前章号 + 1 的关系才算"既有"
        if chapter_int < ch_idx + 1:
            result.append({
                "from": r.get("from", ""),
                "to": r.get("to", ""),
                "type": r.get("type", ""),
                "description": r.get("description", ""),
                "chapter": chapter,
            })
    return result


def parse_relation_check_response(text):
    """解析关系校验结果，返回 (issues, summary)"""
    from .planner_agent import parse_stage_response
    data = parse_stage_response(text)
    if not isinstance(data, dict):
        raise ValueError("关系校验结果不是 JSON 对象")

    issues = []
    for it in data.get("issues", []) or []:
        if not isinstance(it, dict):
            continue
        sev = (it.get("severity") or "low").strip().lower()
        if sev not in ("high", "medium", "low"):
            sev = "low"
        issues.append({
            "severity": sev,
            "from": (it.get("from") or "").strip(),
            "to": (it.get("to") or "").strip(),
            "type": (it.get("type") or "").strip(),
            "description": (it.get("description") or "").strip(),
            "suggestion": (it.get("suggestion") or "").strip(),
        })

    summary = (data.get("summary") or "").strip()
    return issues, summary


# ============================================================
# 修正
# ============================================================

def build_correction_prompt(project, vol_idx, ch_idx, chapter,
                             deviation_report, relation_issues) -> str:
    """构建修正 prompt：携带世界规则与前序大纲，避免修正引入新矛盾"""
    content = (chapter.content or "").strip()
    if len(content) > 15000:
        head = content[:8000]
        tail = content[-5000:]
        content = (
            f"{head}\n……（中段省略 {len(content) - 13000} 字）……\n{tail}"
        )

    plan_text = chapter.plan.to_prompt_text() if chapter.plan else "（无规划）"

    # 世界规则与前序大纲
    world_rules = _collect_world_rules(project, max_chars=20000)
    prev_outlines = _collect_preceding_outlines(
        project, vol_idx, ch_idx, count=5
    )

    # 偏离问题汇总
    dev_lines = []
    if deviation_report and deviation_report.dimensions:
        for d in deviation_report.dimensions:
            if d.status in ("deviated", "missing"):
                dev_lines.append(
                    f"- [{d.status}] "
                    f"{DIMENSION_LABELS.get(d.dimension, d.dimension)}："
                    f"{d.comment}"
                )
    if deviation_report and deviation_report.extra_content:
        dev_lines.append("规划外多出的内容：")
        for e in deviation_report.extra_content:
            dev_lines.append(f"  · {e}")
    dev_text = "\n".join(dev_lines) if dev_lines else "（无重大偏离）"

    # 关系问题
    rel_lines = []
    for it in relation_issues or []:
        rel_lines.append(
            f"- [{it['severity']}] {it['from']} → {it['to']}"
            f"（{it['type']}）：{it['description']}\n"
            f"  建议：{it['suggestion']}"
        )
    rel_text = "\n".join(rel_lines) if rel_lines else "（无关系问题）"

    parts = []

    parts.append(
        "你是资深小说编辑。请根据下面的偏离报告与关系校验结果，"
        "修订本章正文，使其与规划一致、关系时序合理，且不违反既有设定。\n"
    )

    if world_rules:
        parts.append("【L1 世界规则（修订时必须遵守）】")
        parts.append(world_rules)
        parts.append("")

    if prev_outlines:
        parts.append("【前序章节大纲（修订时不得与之矛盾）】")
        parts.append(prev_outlines)
        parts.append("")

    parts.append("【本章规划】")
    parts.append(plan_text)
    parts.append("")

    parts.append("【本章规划】")
    parts.append(plan_text)
    parts.append("")

    # 细纲明确列出作为硬约束（即便 to_prompt_text 已含，也单独再强调一次）
    if chapter.plan and chapter.plan.has_detailed_outline():
        parts.append("【本章细纲（修订时不得删减节拍、不得改变顺序）】")
        for i, step in enumerate(chapter.plan.detailed_outline, 1):
            parts.append(f"  {i}. {step}")
        parts.append("")

    if chapter.plan and chapter.plan.transition_notes:
        parts.append(f"【本章过渡定位】{chapter.plan.transition_notes}")
        parts.append("")

    if chapter.plan and chapter.plan.required_entities:
        re_dict = chapter.plan.required_entities
        re_lines = []
        for k, label in [
            ("characters", "角色"),
            ("locations", "地点"),
            ("items", "物品"),
            ("organizations", "组织"),
        ]:
            names = re_dict.get(k) or []
            if names:
                re_lines.append(f"{label}：{'、'.join(names)}")
        if re_lines:
            parts.append("【本章应出现的实体】")
            parts.extend(re_lines)
            parts.append("")

    parts.append("【本章正文（原文）】")
    parts.append(content)
    parts.append("")

    parts.append("【规划偏离问题】")
    parts.append(dev_text)
    parts.append("")

    parts.append("【关系校验问题】")
    parts.append(rel_text)
    parts.append("")

    parts.append(
        "【修订要求】\n"
        "1. 只做必要修改，不改动与问题无关的部分\n"
        "2. 优先修正「规划外多出内容」——但若这些内容与前序大纲或世界规则一致，"
        "属于合理延续，不得删除\n"
        "3. 修正缺失的规划事件——若本章规划中有事件未发生，应补写\n"
        "4. 修正关系时序问题——若出现「提前建立的关系」，"
        "应改写为当前进度合理的关系\n"
        "5. 修订后的内容不得违反 L1 世界规则\n"
        "6. 修订后的内容不得与前序章节大纲矛盾\n"
        "7. 保留原文本的语言风格与人物语气\n"
        "8. 输出完整修订后的正文，不添加解释、标题或 markdown 标记\n"
        "9. 修订后必须覆盖细纲的所有场景节拍，且顺序与细纲一致；"
        "不得因修正偏离而删减细纲要求的节拍\n"
    )
    parts.append("")
    parts.append(
        "【硬性要求】\n"
        "- 只输出修订后的正文全文\n"
        "- 不要用任何标记包裹\n"
        "- 保持章节开头的衔接自然\n"
        "- 保持章节结尾落在规划指定的钩子上\n"
    )
    parts.append("")
    parts.append("请输出修订后的正文：")

    return "\n".join(parts)


# ============================================================
# 辅助：收集前序上下文
# ============================================================

def _flatten_chapters(project):
    """拍平为 [(vi, ci, vol, ch)]"""
    flat = []
    for vi, vol in enumerate(project.volumes):
        for ci, ch in enumerate(vol.chapters):
            flat.append((vi, ci, vol, ch))
    return flat


def _find_pos(flat, vol_idx, ch_idx):
    for i, (vi, ci, _, _) in enumerate(flat):
        if vi == vol_idx and ci == ch_idx:
            return i
    return -1


def _collect_preceding_outlines(project, vol_idx, ch_idx, count=5):
    """前序 N 章的摘要 + 关键事件"""
    flat = _flatten_chapters(project)
    pos = _find_pos(flat, vol_idx, ch_idx)
    if pos <= 0:
        return ""

    start = max(0, pos - count)
    prev = flat[start:pos]

    lines = []
    for vi, ci, vol, ch in prev:
        summary = (ch.summary or "").strip()
        plan = getattr(ch, "plan", None)
        goal = ""
        key_events = []
        if plan:
            goal = (plan.goal or "").strip()
            key_events = [e for e in (plan.key_events or []) if e]

        if not summary and not goal and not key_events:
            continue

        lines.append(f"第{vi + 1}卷 第{ci + 1}章《{ch.title}》")
        if summary:
            lines.append(f"  摘要：{summary}")
        if goal:
            lines.append(f"  目标：{goal}")
        if key_events:
            lines.append(f"  关键事件：{'；'.join(key_events)}")
        lines.append("")

    return "\n".join(lines).rstrip() if lines else ""


def _collect_world_rules(project, max_chars=20000):
    """L1 世界规则（硬约束），超长时截断"""
    try:
        from .context_builder import build_l1_world
        text = build_l1_world(project)
    except Exception:
        text = ""
    if not text:
        return ""
    if len(text) > max_chars:
        text = text[:max_chars] + f"\n……（已截断，原文字数 {len(text)}）"
    return text


def _collect_relevant_entities(project, vol_idx, ch_idx, max_chars=4000):
    """与当前章相关的实体档案（角色/地点/组织/物品/怪物）"""
    try:
        from .character_index import (
            get_characters_mentioned_in_chapter,
            get_locations_mentioned_in_chapter,
            get_organizations_mentioned_in_chapter,
            get_items_mentioned_in_chapter,
            get_monsters_mentioned_in_chapter,
        )
    except Exception:
        return ""

    chars = get_characters_mentioned_in_chapter(project, vol_idx, ch_idx)
    locs = get_locations_mentioned_in_chapter(project, vol_idx, ch_idx)
    orgs = get_organizations_mentioned_in_chapter(project, vol_idx, ch_idx)
    items = get_items_mentioned_in_chapter(project, vol_idx, ch_idx)
    monsters = get_monsters_mentioned_in_chapter(project, vol_idx, ch_idx)

    lines = []
    for c in chars:
        line = f"· 角色 {c.name}"
        if c.aliases:
            line += f"（别名：{'、'.join(c.aliases[:3])}）"
        if c.personality:
            line += f"｜{c.personality[:80]}"
        if c.is_dead():
            line += "｜【已死亡】"
        lines.append(line)
    for o in orgs:
        lines.append(f"· 组织 {o.name}（{o.nature}）：{o.description[:80]}")
    for l in locs:
        lines.append(f"· 地点 {l.name}（{l.level}）：{l.description[:80]}")
    for i in items:
        lines.append(f"· 物品 {i.name}（{i.type}）：{i.ability[:60]}")
    for m in monsters:
        line = f"· 怪物 {m.name}"
        if m.category:
            line += f"（{m.category}）"
        if m.behavior_ability:
            line += f"：{m.behavior_ability[:80]}"
        lines.append(line)

    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n……（已截断）"
    return text