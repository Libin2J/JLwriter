"""
审核 Agent：对大纲阶段、故事弧、章节规划进行二次审核
"""
from .models import ChapterPlan
from .planner_agent import parse_stage_response
from .key_facts import stringify_parsed

REVIEW_ASPECTS = [
    "一致性", "节奏", "伏笔", "人物", "可执行性", "完整性",
]


def build_planner_stage_review_prompt(stage_id, stage_label, parsed_content,
                                       preset_text, prior_context) -> str:
    content_str = stringify_parsed(parsed_content)
    prompt = f"""你是资深小说策划审稿人。请审查下面这一阶段的设定内容。

#用户预设
{preset_text or "（未指定）"}

#已完成的前序设定
{prior_context or "（本阶段为第一阶段）"}

#当前阶段：{stage_label}
{content_str}

#审查维度
1. 一致性：是否与前序设定矛盾（世界观、力量、人物、势力、专有名词）
2. 完整性：该阶段该有的要素是否齐全
3. 可执行性：后续章节规划能否基于此展开，是否有空泛表述
4. 内在逻辑：力量体系是否有清晰规则，角色动机是否成立
5. 可优化性：是否存在更完美的设定、展开方式和情感爆发点

#输出格式
只输出 JSON，不要 markdown、不要修订内容：
{{
  "_thought": "简要判断，60字以内",
  "overall_score": 0-100,
  "issues": [
    {{
      "severity": "high|medium|low",
      "aspect": "一致性|完整性|可执行性|内在逻辑",
      "description": "问题描述，100字以内",
      "suggestion": "修改方向，100字以内"
    }}
  ],
  "highlights": ["做得好的地方，50字以内"]
}}

#重要
- 不要输出修订后的完整内容。用户会在需要时单独请求修订方案。
- 若发现问题为空，issues 返回 []
- 注意专有名词设定的前后事实逻辑一致性(如前序将‘谐振壳’设定为细胞分子层面的保护，后续设计有‘擦拭谐振壳’的动作，这就是严重错误！)
"""
    return prompt


def build_arc_review_prompt(project, vol_idx) -> str:
    vol = project.volumes[vol_idx]
    arcs_text = []
    for i, arc in enumerate(vol.arcs, 1):
        arcs_text.append(
            f"弧{i}：{arc.name}\n"
            f"  目标：{arc.goal}\n"
            f"  章数：{arc.estimated_chapters}\n"
            f"  转折点：{'；'.join(arc.key_turning_points)}\n"
            f"  埋伏笔：{'；'.join(arc.foreshadowing_to_plant) or '无'}\n"
            f"  收伏笔：{'；'.join(arc.foreshadowing_to_payoff) or '无'}"
        )

    prompt = f"""你是资深小说策划审稿人。请审查下面这一卷的故事弧结构。

##卷信息
{vol.title}
卷摘要：{vol.summary[:800]}

##当前弧结构
{chr(10).join(arcs_text)}

##审查维度
1. 节奏分布：铺垫/冲突/高潮/过渡是否合理，人物形象和情感爆发是否恰当
2. 递进关系：弧与弧之间是否有清晰的升级或转折
3. 伏笔闭环：埋伏笔是否有对应回收
4. 章数合理性：各弧章数是否匹配其内容体量
5. 主线密度：主线推进是否连贯，有无断层

##输出硬性约束
- issues 数量：最多 8 条，按严重程度降序
- description：每条不超过 100 字
- suggestion：每条不超过 100 字
- highlights：最多 5 条，每条不超过 50 字
- _thought：不超过 200 字

##输出格式
只输出 JSON，不要 markdown：
{{
  "_thought": "简要判断，40字以内",
  "overall_score": 0-100,
  "issues": [
    {{
      "severity": "high|medium|low",
      "aspect": "节奏|递进|伏笔|章数|主线",
      "arc_index": 0,
      "description": "≤100字",
      "suggestion": "≤100字"
    }}
  ],
  "highlights": ["≤50字"]
}}"""
    return prompt

def build_setting_alignment_prompt(project, vol_idx, arc_idx, chapters) -> str:
    """
    设定对齐任务：检查一批章节规划是否与设定冲突，
    若有冲突，直接输出修正后的完整章节列表（用于替换）。
    """
    vol = project.volumes[vol_idx]
    arc = vol.arcs[arc_idx]

    # 收集整弧涉及实体（判断设定一致性需要看整条弧的引用）
    all_arc_chapters = [c for c in vol.chapters if c.arc_idx == arc_idx]
    setting_context = _collect_setting_context(project, all_arc_chapters)

    chapters_text = []
    for i, ch in enumerate(chapters):
        plan = ch.plan
        if not plan:
            continue
        block = [
            f"第{i}章（chapter_index={i}）：",
            f"  title: {plan.title}",
            f"  goal: {plan.goal}",
            f"  characters: {plan.characters}",
            f"  key_events: {plan.key_events}",
            f"  foreshadowing: {plan.foreshadowing}",
            f"  ending_hook: {plan.ending_hook}",
            f"  estimated_words: {plan.estimated_words}",
        ]
        req = plan.required_entities or {}
        if req:
            block.append(f"  required_entities: {req}")
        chapters_text.append("\n".join(block))

    prompt = f"""你是小说设定一致性校验员。请对比【世界设定与实体档案】和【章节规划】，找出规划与设定冲突的地方。

#世界设定与实体档案（校验基准，不可违背）
{setting_context}

#当前弧
{arc.name}：{arc.goal}

#待校验的章节规划
{chr(10).join(chapters_text)}

#校验维度
1. 实体名称：角色 / 组织 / 地点 / 物品 / 怪物的名称必须与设定一致；
   若使用了别名，必须确认别名在设定中有记录；
   若引用了未建档的实体，判断是应补充建档还是笔误
2. 力量等级：角色能力、战斗难度必须符合力量体系的等级规则；
   低级角色不得越级碾压高级角色
3. 地点从属：地点的层级、上级关系必须与设定一致
4. 势力关系：组织立场、成员关系必须与设定一致
5. 物品归属：物品的归属者、能力必须与设定一致
6. 怪物能力：怪物的能力、纲目必须与设定一致
7. 死亡状态：已死亡角色不得作为活跃角色出现（回忆/幻象除外）
8. 时间线：角色年龄、经历的时间顺序不得与设定矛盾

#输出要求
- 若所有章节均无冲突，输出：
  {{"has_issues": false, "chapters": []}}
- 若存在冲突，输出完整修正后的所有章节：
  {{"has_issues": true, "chapters": [...]}}

  注意：
  - 修正后的列表必须包含【待校验的章节规划】中的**所有章节**
  - 保持章节数量和顺序不变
  - 只修正有冲突的字段，未冲突的字段原样保留
  - 每章结构：
    {{
      "chapter_index": 0,
      "title": "...",
      "goal": "...",
      "characters": [...],
      "key_events": [...],
      "foreshadowing": [...],
      "ending_hook": "...",
      "estimated_words": 3000
    }}

只输出 JSON 对象，不要 markdown。"""
    return prompt

# ============================================================
# 设定上下文收集（供章节规划审核 / 修正使用）
# ============================================================

def _collect_world_rules(project, max_chars=8000) -> str:
    """提取 L1 世界规则（完整硬约束），超长时截断"""
    try:
        from context_builder import build_l1_world
        text = build_l1_world(project)
    except Exception:
        text = ""
    if not text:
        return ""
    # if len(text) > max_chars:
    #     text = text[:max_chars] + f"\n……（已截断，原文字数 {len(text)}）"
    return text


def _collect_arc_entities(project, arc_chapters, max_chars=4000) -> str:
    """
    收集当前弧所有章节规划中涉及的实体，从 project 中查完整档案。
    缺失的实体单独列出，供审核发现"引用了未建档的实体"。
    """
    # 1. 收集引用的实体名
    char_names = set()
    loc_names = set()
    item_names = set()
    org_names = set()
    monster_names = set()

    for ch in arc_chapters:
        plan = getattr(ch, "plan", None)
        if not plan:
            continue
        for n in plan.characters or []:
            n = str(n).strip()
            if n:
                char_names.add(n)
        req = plan.required_entities or {}
        for n in req.get("characters") or []:
            char_names.add(str(n).strip())
        for n in req.get("locations") or []:
            loc_names.add(str(n).strip())
        for n in req.get("items") or []:
            item_names.add(str(n).strip())
        for n in req.get("organizations") or []:
            org_names.add(str(n).strip())
        for n in req.get("monsters") or []:
            monster_names.add(str(n).strip())

    # 2. 查档案
    char_lookup = {c.name: c for c in project.characters}
    loc_lookup = {l.name: l for l in project.locations}
    item_lookup = {i.name: i for i in project.items}
    org_lookup = {o.name: o for o in project.organizations}
    monster_lookup = {m.name: m for m in project.monsters}

    lines = []

    # 已建档的实体
    for n in sorted(char_names):
        c = char_lookup.get(n)
        if c:
            line = f"· 角色 {c.name}"
            if c.aliases:
                line += f"（别名：{'、'.join(c.aliases[:3])}）"
            if c.power_level:
                line += f"｜等级：{c.power_level}"
            if c.health:
                line += f"｜健康：{c.health}"
            if c.is_dead():
                line += "｜【已死亡】"
            lines.append(line)

    for n in sorted(org_names):
        o = org_lookup.get(n)
        if o:
            line = f"· 组织 {o.name}"
            if o.nature:
                line += f"（{o.nature}）"
            if o.members:
                line += f"｜成员：{'、'.join(o.members[:5])}"
            lines.append(line)

    for n in sorted(loc_names):
        l = loc_lookup.get(n)
        if l:
            line = f"· 地点 {l.name}"
            if l.level:
                line += f"（{l.level}）"
            if l.parent:
                line += f"｜上级：{l.parent}"
            lines.append(line)

    for n in sorted(item_names):
        i = item_lookup.get(n)
        if i:
            line = f"· 物品 {i.name}"
            if i.type:
                line += f"（{i.type}）"
            if i.owner:
                line += f"｜归属：{i.owner}"
            lines.append(line)

    for n in sorted(monster_names):
        m = monster_lookup.get(n)
        if m:
            line = f"· 怪物 {m.name}"
            if m.category:
                line += f"（{m.category}）"
            if m.behavior_ability:
                line += f"｜能力：{m.behavior_ability}"
            lines.append(line)

    # 未建档的引用
    missing = []
    for n in sorted(char_names - set(char_lookup.keys())):
        if n:
            missing.append(f"角色「{n}」")
    for n in sorted(org_names - set(org_lookup.keys())):
        if n:
            missing.append(f"组织「{n}」")
    for n in sorted(loc_names - set(loc_lookup.keys())):
        if n:
            missing.append(f"地点「{n}」")
    for n in sorted(item_names - set(item_lookup.keys())):
        if n:
            missing.append(f"物品「{n}」")
    for n in sorted(monster_names - set(monster_lookup.keys())):
        if n:
            missing.append(f"怪物「{n}」")

    if missing:
        lines.append("")
        lines.append("#未建档的实体引用（规划中提及但项目中不存在）")
        lines.append("、".join(missing))

    text = "\n".join(lines).strip()
    # if len(text) > max_chars:
    #     text = text[:max_chars] + "\n……（已截断）"
    return text


def _collect_setting_context(project, arc_chapters) -> str:
    """组装完整的设定上下文（世界规则 + 相关实体）"""
    parts = []
    rules = _collect_world_rules(project)
    if rules:
        parts.append(rules)
        parts.append("")
    entities = _collect_arc_entities(project, arc_chapters)
    if entities:
        parts.append("#本弧涉及的实体档案")
        parts.append(entities)
        parts.append("")
    return "\n".join(parts).rstrip()

def parse_setting_alignment_response(text):
    """解析设定对齐结果，返回 dict: {has_issues, chapters}"""
    from .planner_agent import parse_stage_response
    data = parse_stage_response(text)
    if not isinstance(data, dict):
        raise ValueError("对齐结果不是 JSON 对象")

    has_issues = bool(data.get("has_issues", False))
    chapters = data.get("chapters") or []
    if not isinstance(chapters, list):
        chapters = []

    return {"has_issues": has_issues, "chapters": chapters}


def build_chapter_batch_review_prompt(project, vol_idx, arc_idx,
                                      chapters, preceding_summary,
                                      is_first_batch=True) -> str:
    """
    chapters：本批要审核的章节列表
    preceding_summary：本批之前章节的滚动摘要（不含本批）
    """
    vol = project.volumes[vol_idx]
    arc = vol.arcs[arc_idx]

    chapters_text = []
    for i, ch in enumerate(chapters):
        plan = ch.plan
        if not plan:
            continue
        chapters_text.append(
            f"第{i + 1}章 {plan.title}\n"
            f"  目标：{plan.goal}\n"
            f"  人物：{'、'.join(plan.characters)}\n"
            f"  事件：{'；'.join(plan.key_events)}\n"
            f"  伏笔：{'；'.join(plan.foreshadowing) or '无'}\n"
            f"  钩子：{plan.ending_hook}"
        )

    batch_scope = "首批" if is_first_batch else "续批"
    continuity_req = (
        "本批为弧的首批，重点审查与弧目标的对齐"
        if is_first_batch
        else "本批为续批，重点审查与【前序摘要】的衔接，有无重复上文情节"
    )

    # 无前序摘要时不渲染该段，避免误导
    if preceding_summary and preceding_summary.strip() and "（本批为本弧" not in preceding_summary:
        preceding_block = f"""##前序摘要（本批之前的章节，仅供衔接参考）
{preceding_summary}
"""
    else:
        preceding_block = ""

    prompt = f"""你是资深小说策划审稿人。请审查下面这一批章节规划。

##卷信息
{vol.title} · {vol.summary[:400]}

##当前弧
{arc.name}
弧目标：{arc.goal}
弧转折点：{'；'.join(arc.key_turning_points)}

{preceding_block}
##本批章节（{batch_scope}，共 {len(chapters)} 章，即本次审核对象）
{chr(10).join(chapters_text)}

##审查重点
{continuity_req}

##审查维度
1. 弧目标对齐：本批章节是否围绕弧目标推进
2. 节奏：铺垫/冲突/高潮的分布
3. 伏笔：埋伏笔是否清晰、能否衔接后续
4. 人物：出场角色是否合理
5. 事件推进：每章是否有实质推进
6. 钩子：章末钩子是否多样有力
7. 与【前序摘要】的衔接：是否重复上文已发生的情节（若有前序摘要）

##输出格式
只输出 JSON，不要 markdown、不要修订内容：
{{
  "_thought": "简要判断，60字以内",
  "overall_score": 0-100,
  "issues": [
    {{
      "severity": "high|medium|low",
      "aspect": "弧目标|节奏|伏笔|人物|事件|钩子|衔接",
      "chapter_index": 0,
      "description": "问题描述，50字以内",
      "suggestion": "修改方向，50字以内"
    }}
  ],
  "highlights": ["优点，50字以内"]
}}

【重要】
- 不要输出修订后的章节列表
- chapter_index 是本批内的索引（从 0 开始），不是全弧的索引"""
    return prompt


def parse_review_response(text: str) -> dict:
    """解析审核结果（不含修订内容）"""
    data = parse_stage_response(text)
    if not isinstance(data, dict):
        raise ValueError("审核结果不是 JSON 对象")

    score = data.get("overall_score", 0)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    score = max(0, min(100, score))

    issues = []
    for it in data.get("issues", []) or []:
        if not isinstance(it, dict):
            continue
        severity = (it.get("severity") or "low").strip().lower()
        if severity not in ("high", "medium", "low"):
            severity = "low"
        issues.append({
            "severity": severity,
            "aspect": (it.get("aspect") or "其他").strip(),
            "arc_index": it.get("arc_index"),
            "chapter_index": it.get("chapter_index"),
            "description": (it.get("description") or "").strip(),
            "suggestion": (it.get("suggestion") or "").strip(),
        })

    return {
        "overall_score": score,
        "thought": (data.get("_thought") or "").strip(),
        "issues": issues,
        "highlights": [str(x).strip() for x in (data.get("highlights") or []) if str(x).strip()],
    }


def build_arc_revision_prompt(project, vol_idx, issues) -> str:
    """基于审核意见生成最小化 patch"""
    vol = project.volumes[vol_idx]

    arcs_text = []
    for i, arc in enumerate(vol.arcs, 1):
        arcs_text.append(
            f"弧{i - 1}：{arc.name}\n"
            f"  goal: {arc.goal}\n"
            f"  estimated_chapters: {arc.estimated_chapters}\n"
            f"  key_turning_points: {'；'.join(arc.key_turning_points)}\n"
            f"  foreshadowing_to_plant: {'；'.join(arc.foreshadowing_to_plant) or '无'}\n"
            f"  foreshadowing_to_payoff: {'；'.join(arc.foreshadowing_to_payoff) or '无'}"
        )

    issues_text = []
    for i, it in enumerate(issues):
        line = f"{i + 1}. [{it['severity']}] {it['aspect']}"
        if it.get("arc_index") is not None:
            line += f"（弧{it['arc_index']}）"
        line += f"\n   问题：{it['description']}\n   建议：{it['suggestion']}"
        issues_text.append(line)

    prompt = f"""你是小说设定修正助手。请根据一致性校验意见修正当前阶段的内容，输出最小化的修订 patch。

#当前弧结构
{chr(10).join(arcs_text)}

#审核意见
{chr(10).join(issues_text)}

#修订要求
1. 只修改确实需要改变的字段，不要重写整个弧
2. 每个 patch 指定：arc_index（从 0 开始）、field、new_value
3. 若某意见认为当前内容已足够好，可以跳过该意见
4. 只输出发生变化的最小 patch 集

##field 允许值
name / goal / estimated_chapters / key_turning_points / foreshadowing_to_plant / foreshadowing_to_payoff

##new_value 格式
- name / goal：字符串
- estimated_chapters：整数
- key_turning_points / foreshadowing_to_plant / foreshadowing_to_payoff：字符串数组

#输出格式
只输出 JSON，不要 markdown：
{{
  "_thought": "简要说明，100字以内",
  "patches": [
    {{"arc_index": 0, "field": "goal", "new_value": "修订后的目标"}},
    {{"arc_index": 1, "field": "key_turning_points", "new_value": ["转折1", "转折2"]}}
  ]
}}"""
    return prompt


def build_planner_stage_revision_prompt(stage_id, stage_label, parsed_content, issues) -> str:
    """单阶段修订 patch"""
    content_str = stringify_parsed(parsed_content)

    issues_text = []
    for i, it in enumerate(issues):
        issues_text.append(
            f"{i + 1}. [{it['severity']}] {it['aspect']}\n"
            f"   问题：{it['description']}\n   建议：{it['suggestion']}"
        )

    # 判断该阶段是文本型还是列表型
    is_text_stage = stage_id in ("premise", "background", "power_system", "outline")

    if is_text_stage:
        field_hint = """#输出格式
只输出 JSON：
{{
  "_thought": "简要说明，100字以内",
  "patches": [
    {{"field": "内容字段名", "new_value": "仅输出修订后的完整文本"}}
  ]
}}
内容字段名：premise / story_background / power_system / outline 之一（与当前阶段一致）"""
    else:
        field_hint = """#输出格式
只输出 JSON：
{{
  "_thought": "简要说明",
  "patches": [
    {{"target_index": 0, "field": "字段名", "new_value": "修订后的值"}}
  ]
}}
- 列表类阶段（characters / organizations / locations / items）：
  - target_index 为列表中元素的索引（从 0 开始）
  - field 为需要修改的具体字段名
  - 若需新增元素，用 target_index = -1 且 new_value 为完整对象
  - 若需删除元素，用 target_index = 具体索引 且 new_value = null"""

    prompt = f"""你是小说策划。请针对下面这一阶段的审核意见，输出最小化修订 patch。

#当前阶段：{stage_label}
{content_str}

#审核意见
{chr(10).join(issues_text)}

#修订要求
1. 只修改确实需要改变的字段
2. 不重写未涉及问题的部分
3. 保持字段名与结构一致

{field_hint}"""
    return prompt


def build_chapter_batch_revision_prompt(project, vol_idx, arc_idx, chapters, issues) -> str:
    vol = project.volumes[vol_idx]
    arc = vol.arcs[arc_idx]

    chapters_text = []
    for i, ch in enumerate(chapters):
        plan = ch.plan
        if not plan:
            continue
        chapters_text.append(
            f"第{i}章（chapter_index={i}）：\n"
            f"  title: {plan.title}\n"
            f"  goal: {plan.goal[:60]}\n"
            f"  characters: {plan.characters}\n"
            f"  key_events: {plan.key_events}\n"
            f"  foreshadowing: {plan.foreshadowing}\n"
            f"  ending_hook: {plan.ending_hook[:40]}"
        )

    issues_text = []
    for i, it in enumerate(issues):
        line = f"{i + 1}. [{it['severity']}] {it['aspect']}"
        if it.get("chapter_index") is not None:
            line += f"（第{it['chapter_index']}章）"
        line += f"\n   问题：{it['description']}\n   建议：{it['suggestion']}"
        issues_text.append(line)

    prompt = f"""你是小说策划。请针对下面这一批章节的审核意见，输出最小化修订 patch。

#当前弧
{arc.name}：{arc.goal[:100]}

#章节列表（chapter_index 从 0 开始）
{chr(10).join(chapters_text)}

#审核意见
{chr(10).join(issues_text)}

#修订要求】
1. 只修改需要改变的章节与字段
2. 未涉及问题的章节不要出现在 patch 中
3. 每个 patch 指定：chapter_index、field、new_value
4. patch 数量控制在 20 条以内
5. 保持每条 new_value 简洁（goal/hook 不超过 60 字）
6. chapter_index 必须使用【章节列表】中给出的编号（批内索引），不要使用全弧编号

##field 允许值
title / goal / characters / key_events / foreshadowing / ending_hook / estimated_words

##new_value 格式
- title / goal / ending_hook：字符串（≤60字）
- characters / key_events / foreshadowing：字符串数组
- estimated_words：整数

#输出格式
只输出 JSON，不要 markdown：
{{
  "_thought": "≤30字",
  "patches": [
    {{"chapter_index": 3, "field": "ending_hook", "new_value": "..."}},
    {{"chapter_index": 5, "field": "key_events", "new_value": ["..."]}}
  ]
}}"""
    return prompt

def parse_patch_response(text: str) -> list:
    """解析 patch 列表"""
    data = parse_stage_response(text)
    patches = data.get("patches", []) if isinstance(data, dict) else []
    result = []
    for p in patches:
        if not isinstance(p, dict):
            continue
        field = (p.get("field") or "").strip()
        if not field:
            continue
        result.append({
            "arc_index": p.get("arc_index"),
            "chapter_index": p.get("chapter_index"),
            "target_index": p.get("target_index"),
            "field": field,
            "new_value": p.get("new_value"),
        })
    return result


def apply_arc_patches(vol, patches) -> dict:
    """将 patch 应用到卷的弧结构"""
    stats = {"applied": 0, "skipped": 0}
    for p in patches:
        idx = p.get("arc_index")
        if idx is None:
            stats["skipped"] += 1
            continue
        idx = int(idx)
        if idx < 0 or idx >= len(vol.arcs):
            stats["skipped"] += 1
            continue
        arc = vol.arcs[idx]
        field = p["field"]
        value = p["new_value"]

        try:
            if field in ("name", "goal"):
                if isinstance(value, str):
                    setattr(arc, field, value.strip())
                    stats["applied"] += 1
                else:
                    stats["skipped"] += 1
            elif field == "estimated_chapters":
                arc.estimated_chapters = int(value)
                stats["applied"] += 1
            elif field in ("key_turning_points", "foreshadowing_to_plant",
                           "foreshadowing_to_payoff"):
                if isinstance(value, list):
                    setattr(arc, field,
                            [str(x).strip() for x in value if str(x).strip()])
                    stats["applied"] += 1
                else:
                    stats["skipped"] += 1
            else:
                stats["skipped"] += 1
        except Exception:
            stats["skipped"] += 1
    return stats


def apply_chapter_patches(vol, arc_idx, patches) -> dict:
    """将 patch 应用到某弧的章节规划"""
    stats = {"applied": 0, "skipped": 0}
    arc_chapters = [c for c in vol.chapters if c.arc_idx == arc_idx]
    for p in patches:
        ci = p.get("chapter_index")
        if ci is None:
            stats["skipped"] += 1
            continue
        ci = int(ci)
        if ci < 0 or ci >= len(arc_chapters):
            stats["skipped"] += 1
            continue
        ch = arc_chapters[ci]
        if not ch.plan:
            ch.plan = ChapterPlan(title=ch.title)
        plan = ch.plan
        field = p["field"]
        value = p["new_value"]

        try:
            if field in ("title", "goal", "ending_hook"):
                if isinstance(value, str):
                    setattr(plan, field, value.strip())
                    if field == "title":
                        ch.title = plan.title
                    stats["applied"] += 1
                else:
                    stats["skipped"] += 1
            elif field in ("characters", "key_events", "foreshadowing"):
                if isinstance(value, list):
                    setattr(plan, field,
                            [str(x).strip() for x in value if str(x).strip()])
                    stats["applied"] += 1
                else:
                    stats["skipped"] += 1
            elif field == "estimated_words":
                plan.estimated_words = int(value)
                stats["applied"] += 1
            else:
                stats["skipped"] += 1
        except Exception:
            stats["skipped"] += 1
    return stats


def apply_stage_patches(parsed: dict, patches, stage_id) -> dict:
    """将 patch 应用到单阶段结果，返回新的 dict"""
    result = dict(parsed)
    applied = 0
    skipped = 0

    is_text_stage = stage_id in ("premise", "background", "power_system", "outline")

    if is_text_stage:
        for p in patches:
            field = p["field"]
            if field in ("premise", "story_background", "power_system", "outline"):
                if isinstance(p["new_value"], str):
                    result[field] = p["new_value"]
                    applied += 1
                else:
                    skipped += 1
            else:
                skipped += 1
        return {"data": result, "applied": applied, "skipped": skipped}

    # 列表类阶段
    list_fields = {
        "characters": "characters",
        "organizations": "organizations",
        "locations": "locations",
        "items": "items",
    }
    for p in patches:
        target_idx = p.get("target_index")
        if target_idx is None:
            skipped += 1
            continue
        target_idx = int(target_idx)

        # 找到该阶段的主列表字段
        main_field = None
        for k in list_fields:
            if k in result and isinstance(result[k], list):
                main_field = k
                break
        if not main_field:
            skipped += 1
            continue

        items_list = result[main_field]
        if target_idx == -1:
            # 新增
            if isinstance(p["new_value"], dict):
                items_list.append(p["new_value"])
                applied += 1
            else:
                skipped += 1
        elif 0 <= target_idx < len(items_list):
            if p["new_value"] is None:
                # 删除
                items_list.pop(target_idx)
                applied += 1
            elif isinstance(items_list[target_idx], dict):
                items_list[target_idx][p["field"]] = p["new_value"]
                applied += 1
            else:
                skipped += 1
        else:
            skipped += 1

    return {"data": result, "applied": applied, "skipped": skipped}