"""
细纲展开（ReAct 阶段一）：
基于章节规划 + 全局实体名册，让 LLM 输出细纲、需要的实体清单、过渡说明
"""
import json
from .models import ChapterPlan
from .planner_agent import build_golden_three_hint

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


# ============================================================
# 全局实体名册
# ============================================================

def build_entity_roster(project, max_per_type=80) -> str:
    """
    构建全局实体名册：每个实体只给"名称 + 一句话"，
    供 LLM 选择本章需要哪些实体。
    """
    parts = []

    if project.characters:
        parts.append("【角色名册】")
        for c in project.characters[:max_per_type]:
            line = f"- {c.name}"
            if c.aliases:
                line += f"（别名：{'、'.join(c.aliases[:3])}）"
            if c.personality:
                line += f"：{c.personality[:50]}"
            if c.is_dead():
                line += "｜【已死亡】"
            parts.append(line)
        parts.append("")

    if project.monsters:
        parts.append("【怪物名册】")
        for m in project.monsters[:max_per_type]:
            line = f"- {m.name}"
            if m.category:
                line += f"（{m.category}）"
            if m.behavior_ability:
                line += f"：{m.behavior_ability[:40]}"
            parts.append(line)
        parts.append("")

    if project.locations:
        parts.append("【地点名册】")
        for l in project.locations[:max_per_type]:
            line = f"- {l.name}"
            if l.level:
                line += f"（{l.level}）"
            if l.description:
                line += f"：{l.description[:40]}"
            parts.append(line)
        parts.append("")

    if project.organizations:
        parts.append("【组织名册】")
        for o in project.organizations[:max_per_type]:
            line = f"- {o.name}"
            if o.nature:
                line += f"（{o.nature}）"
            if o.description:
                line += f"：{o.description[:50]}"
            parts.append(line)
        parts.append("")

    if project.items:
        parts.append("【物品名册】")
        for i in project.items[:max_per_type]:
            line = f"- {i.name}"
            if i.type:
                line += f"（{i.type}）"
            if i.ability:
                line += f"：{i.ability[:40]}"
            parts.append(line)
        parts.append("")

    if not parts:
        return "（暂无任何已建档实体）"
    return "\n".join(parts).rstrip()


# ============================================================
# Prompt 构建
# ============================================================

def build_detailed_outline_prompt(project, vol_idx, ch_idx,
                                   prev_outline_count=3,
                                   enable_golden_three=False) -> str:
    """构建细纲展开 prompt"""
    vol = project.volumes[vol_idx]
    ch = vol.chapters[ch_idx]
    plan = ch.plan

    # 后续 N 章规划
    following_plans_text = _collect_following_plans(
        project, vol_idx, ch_idx, count=5
    )
    following_new_entities = _collect_following_new_entities(
        project, vol_idx, ch_idx, count=5
    )

    # 定位当前章所属的弧
    arc = None
    arc_idx = getattr(ch, "arc_idx", -1)
    if 0 <= arc_idx < len(vol.arcs):
        arc = vol.arcs[arc_idx]

    if not plan:
        return ""

    # L1 世界规则
    try:
        from .context_builder import build_l1_world
        world_rules = build_l1_world(project)
    except Exception:
        world_rules = ""
    # if len(world_rules) > 6000:
    #     world_rules = world_rules[:6000] + "\n……（已截断）"

    # 前序章节摘要
    prev_lines = []
    flat = []
    for vi, v in enumerate(project.volumes):
        for ci, c in enumerate(v.chapters):
            flat.append((vi, ci, c))
    pos = next((i for i, (vi, ci, _) in enumerate(flat)
                if vi == vol_idx and ci == ch_idx), -1)
    if pos > 0:
        start = max(0, pos - prev_outline_count)
        for vi, ci, pc in flat[start:pos]:
            summary = (pc.summary or "").strip()
            goal = ""
            if pc.plan and pc.plan.goal:
                goal = pc.plan.goal
            if summary or goal:
                prev_lines.append(
                    f"第{vi + 1}卷 第{ci + 1}章《{pc.title}》："
                    f"{summary or goal}"
                )
    prev_text = "\n".join(prev_lines) if prev_lines else "（本章为开篇或前序无摘要）"

    # 全局实体名册
    roster = build_entity_roster(project)

    # 上一章正文（若本章无正文）
    prev_content_block = ""
    if not (ch.content or "").strip() and pos > 0:
        _, _, prev_ch = flat[pos - 1]
        prev_content = (prev_ch.content or "").strip()
        if prev_content:
            if len(prev_content) > 8000:
                prev_content = prev_content[-8000:]
            prev_content_block = (
                "【上一章正文（本章开篇需自然衔接）】\n"
                + prev_content
            )

    plan_text = plan.to_prompt_text()
    estimated_words = plan.estimated_words or 3000
    preference = (plan.chapter_preference or "").strip()

    parts = []
    parts.append(
        "你是小说导演。请为下面这一章展开【细纲】，并明确列出本章需要的所有实体。\n"
    )
    parts.append(
        "#工作流程\n"
        "1. 先通读 L1 世界规则、章节规划、前序摘要，理解故事进展\n"
        "2. 阅读【所处卷与弧】，明确本章在整卷、整弧中的位置：\n"
        "   - 本章服务于弧目标的哪一部分？\n"
        "   - 弧的关键转折点是否落在本章或附近章节？\n"
        "   - 本章是否需要埋伏笔或回收伏笔？\n"
        "3. 阅读【后续章节规划】，识别本章需要为哪些后续情节做铺垫：\n"
        "   - 后续将登场的<角色>，本章是否需要<提前埋下伏笔或至少不与之矛盾>\n"
        "   - 后续将发生的<关键事件>，本章是否需要<构建合理的前提>\n"
        "   - 后续将揭示的<设定>，本章是否需要<按世界观逻辑展现蛛丝马迹>\n"
        "4. 思考本章的剧情走向：从哪里切入、如何推进、在哪里收尾\n"
        "5. 把章节规划剧情构思扩展为 3-6 个连续完整的剧情场景节拍（细纲），每个节拍需要包含直接角色、间接角色和故事情节\n"
        "6. 从【全局实体名册】中挑选本章需要的所有实体\n"
        "   -（角色 / 地点 / 物品 / 组织 / 怪物——怪物名册单独列出）\n"
        "   - 包括直接出场、间接提及、只作为背景的\n"
        "   - 若名册中没有某个必需的新实体，在 required_entities 中标注为 new\n"
        "7. 说明本章作为过渡的作用\n"
    )
    parts.append("")

    if world_rules:
        parts.append("#L1 世界规则（硬约束）")
        parts.append(world_rules)
        parts.append("")

    # ============ 所处卷与弧 ============
    loc_lines = [f"#所处卷与弧"]
    loc_lines.append(f"第{vol_idx + 1}卷《{vol.title}》")
    if vol.summary.strip():
        loc_lines.append(f"卷摘要：{vol.summary.strip()}")

    if arc:
        loc_lines.append("")
        loc_lines.append(f"所属弧：弧{arc_idx + 1} {arc.name}")
        if arc.goal:
            loc_lines.append(f"弧目标：{arc.goal}")
        if arc.key_turning_points:
            loc_lines.append(
                f"弧关键转折点：{'；'.join(arc.key_turning_points)}"
            )
        if arc.foreshadowing_to_plant:
            loc_lines.append(
                f"本弧需埋伏笔：{'、'.join(arc.foreshadowing_to_plant)}"
            )
        if arc.foreshadowing_to_payoff:
            loc_lines.append(
                f"本弧需回收伏笔：{'、'.join(arc.foreshadowing_to_payoff)}"
            )
        loc_lines.append(
            "说明：本章细纲必须服务于弧目标，并为弧内的转折点做铺垫或推进；"
            "若本章涉及埋设/回收伏笔，必须在细纲中安排对应节拍。"
        )

        # 前后弧衔接提示
        if arc_idx > 0:
            prev_arc = vol.arcs[arc_idx - 1]
            loc_lines.append(
                f"前序弧：{prev_arc.name}（{prev_arc.goal[:80]}）"
            )
        if arc_idx + 1 < len(vol.arcs):
            next_arc = vol.arcs[arc_idx + 1]
            loc_lines.append(
                f"后续弧：{next_arc.name}（{next_arc.goal[:80]}）"
            )
    else:
        loc_lines.append("")
        loc_lines.append(
            "（本章尚未归属任何弧；细纲应基于卷摘要与本章规划展开）"
        )

    parts.append("\n".join(loc_lines))
    parts.append("")

    parts.append("#本章规划")
    parts.append(plan_text)
    parts.append("")

    parts.append("#字数规划")
    parts.append(
        f"本章目标字数：约 {estimated_words} 字。\n"
    )
    parts.append("")

    if preference:
        preference_block = (
            f"#章节偏好：{preference}\n"
            f"本章的侧重点应围绕「{preference}」展开：\n"
        )
        pref_guidance = {
            "日常": (
                "以角色互动、生活细节、轻松场景为主；"
                "节奏舒缓，可以慢，但不能无聊；"
                "细纲应侧重人物关系推进、情感变化、细节刻画，"
                "避免大段战斗或强烈冲突。"
            ),
            "战斗": (
                "以对抗、冲突、招式、力量对撞为主；"
                "节奏紧凑，动作感强；"
                "细纲应侧重战斗的起势、交锋、转折、胜负或撤退，"
                "避免生活化铺垫拖慢节奏。"
            ),
            "抒情": (
                "以情感表达、回忆、内心独白、氛围渲染为主；"
                "节奏舒缓，重意境；"
                "细纲应侧重情感触发点、回忆片段、氛围转折，"
                "避免高强度冲突或快节奏推进。"
            ),
            "紧张": (
                "以压力累积、时间紧迫、危险逼近为主；"
                "节奏快，悬念层层递进；"
                "细纲应侧重危机升级、时间压力、倒计时事件，"
                "避免轻松日常或节奏断裂。"
            ),
            "悬疑": (
                "以谜题铺设、线索隐藏、真相逼近为主；"
                "信息释放克制，节奏有张有弛；"
                "细纲应侧重线索埋设、误导性线索、认知反转，"
                "避免过早揭示答案。"
            ),
            "恐怖": (
                "以压抑氛围、未知威胁、心理恐惧为主；"
                "节奏缓中带惊，重在氛围铺陈；"
                "细纲应侧重环境诡异、感官异常、渐进式恐惧，"
                "避免直白的血腥或快节奏战斗。"
            ),
            "热血": (
                "以爆发、斗志、逆袭、燃点为主；"
                "节奏强推，情绪高昂；"
                "细纲应侧重势能积累与爆发节点，"
                "避免平铺直叙或情绪低迷。"
            ),
            "温情": (
                "以温暖、治愈、人际关系的正向互动为主；"
                "节奏舒缓，情感饱满；"
                "细纲应侧重互动细节、无声默契、情感转折，"
                "避免激烈冲突或阴暗情节。"
            ),
            "压抑": (
                "以沉重、绝望、压迫感为主；"
                "节奏沉滞，氛围浓稠；"
                "细纲应侧重困境加深、选择的艰难，"
                "避免轻松或搞笑元素。"
            ),
            "幽默": (
                "以轻松、诙谐、反差、意外为主；"
                "节奏轻快，笑点密集；"
                "细纲应侧重反差、误会、吐槽、意外，"
                "避免严肃沉重内容。"
            ),
            "史诗": (
                "以宏大、壮阔、命运感为主；"
                "节奏有铺有扬，气象宏阔；"
                "细纲应侧重全局视角、关键节点、历史厚度，"
                "避免局限于细枝末节。"
            ),
            "过渡": (
                "以承接前后、场景转换、状态更新为主；"
                "节奏平稳，不做高潮；"
                "细纲应侧重信息交代、场景转换、状态更新，"
                "避免强行安排冲突或爽点。"
            ),
        }
        guidance = pref_guidance.get(preference, (
            f"以「{preference}」为本章核心侧重展开细纲，"
            f"其它元素作为辅助，不喧宾夺主。"
        ))
        preference_block += guidance + "\n"
        parts.append(preference_block)
        parts.append("")
    else:
        parts.append(
            "#章节偏好：自由发挥\n"
            "本章未指定偏好，请根据规划内容与故事节奏自行决定侧重方向。\n"
        )
        parts.append("")

    parts.append("#前序章节摘要")
    parts.append(prev_text)
    parts.append("")

    if prev_content_block:
        parts.append(prev_content_block)
        parts.append("")

    if following_plans_text:
        parts.append("#后续章节规划（本章需为其做铺垫）")
        parts.append(following_plans_text)
        parts.append("")

    if following_new_entities:
        type_label = {
            "character": "角色",
            "monster": "怪物",
        }
        entity_lines = []
        for item in following_new_entities:
            label = type_label.get(item["type"], item["type"])
            entity_lines.append(
                f"- 【{label}】{item['name']}"
                f"（首次出现于{item['first_appear_in']}）"
            )
        parts.append("#后续章节将登场但尚未建档的角色/怪物")
        parts.append(
            "这些实体会在后续章节出场。本章若与之相关，"
            "应在铺垫中提及，或在 required_entities 的 new_entities 中列出，"
            "避免后续突兀登场："
        )
        parts.extend(entity_lines)
        parts.append("")

    parts.append("#全局实体名册（本章实体必须从此处选择）")
    parts.append(roster)
    parts.append("")

    if enable_golden_three and vol_idx == 0 and ch_idx <= 2:
        parts.append(build_golden_three_hint("detailed_outline"))
        parts.append("")

    parts.append(
        "#输出格式："
        "【输出严格 JSON】（不要 markdown，不要额外说明）：\n"
        "{\n"
        '  "_thought": "剧情构思，200-400字",\n'
        '  "detailed_outline": [\n'
        '    "节拍1：主角在竹林练剑，回忆师父教导……",\n'
        '    "节拍2：收到传信，得知师父遇险……",\n'
        '    "节拍3：决定下山，与赵灵儿告别……"\n'
        "  ],\n"
        '  "required_entities": {\n'
        '    "characters": ["角色1", "角色2"...间接出场的角色同样承担信息节点，必须列出],\n'
        '    "monsters": ["怪物1"],\n'
        '    "locations": ["地点1"],\n'
        '    "items": ["物品1"],\n'
        '    "organizations": ["组织1"],\n'
        '    "new_entities": ['
        '    {"type": "character", "name": "某某", "description": "新角色的初步设定"},'
        '    {"type": "monster", "name": "某某兽", "description": "新怪物的外形与能力"}'
        '    ]\n'
        "  },\n"
        '  "transition_notes": "本章作为过渡章，应避免引入新人物，聚焦主角内心的挣扎"\n'
        "}\n"
    )
    parts.append("")
    parts.append(
        "#硬性要求\n"
        "- 细纲的每个节拍都应服务于【章节偏好】的侧重点，"
        "不得喧宾夺主或偏离偏好\n"
        "- detailed_outline 必须 3-6 条，按时间顺序排列, 综合字数规划进行设计\n"
        "- 每条细纲是一句话，描述一个场景节拍\n"
        "- required_entities 尽量完整覆盖：直接出场 + 间接提及 + 背景性实体\n"
        "- 已死亡的实体不得出现在 required_entities 中（除非是回忆场景）\n"
        "- 名册中已有实体的名称必须完全一致，不得简写或别名\n"
        "- 若某实体确实不在名册中，放入 new_entities\n"
        "- transition_notes 用一句话说明本章的过渡作用\n"
        "- monsters 列出本章出现的所有怪物（包括作为对手、威胁、环境危险、被提及的传说怪物）\n"
        "- 若本章需要提及后续章节中尚未建档的角色或怪物，将其加入 new_entities，并在细纲中安排合理的提及/铺垫\n"
        "\n"
        "#铺垫要求\n"
        "- 若【后续章节规划】中出现新角色，本章若与之相关，"
        "应在细纲中安排该角色的引入契机（哪怕是侧面提及）\n"
        "- 若【后续章节规划】中的关键事件需要前提，本章应安排合理铺垫\n"
        "- 若本章与后续章节存在时间/空间跳跃，应在细纲中交代过渡\n"
        "- 不得在细纲中安排与【后续章节规划】矛盾的情节\n"
        "- 若【后续章节将登场但尚未建档的角色】中有角色与本章相关，应将其加入 required_entities 的 new_entities 中\n"
    )

    return "\n".join(parts)


def _collect_following_plans(project, vol_idx, ch_idx, count=5):
    """
    收集当前章之后 N 章的规划概览。
    用于让 LLM 知道"本章需要为后续哪些情节做铺垫"。
    返回格式化文本，无后续章节时返回空字符串。
    """
    flat = []
    for vi, vol in enumerate(project.volumes):
        for ci, ch in enumerate(vol.chapters):
            flat.append((vi, ci, vol, ch))

    cur_pos = None
    for i, (vi, ci, _, _) in enumerate(flat):
        if vi == vol_idx and ci == ch_idx:
            cur_pos = i
            break
    if cur_pos is None:
        return ""

    following = flat[cur_pos + 1: cur_pos + 1 + count]
    if not following:
        return ""

    lines = []
    for vi, ci, vol, ch in following:
        plan = getattr(ch, "plan", None)
        block = [f"第{vi + 1}卷 第{ci + 1}章《{ch.title}》"]

        summary = (ch.summary or "").strip()
        if summary:
            block.append(f"  大纲：{summary[:200]}")

        if plan:
            if plan.goal:
                block.append(f"  目标：{plan.goal[:150]}")
            if plan.characters:
                block.append(f"  出场人物：{'、'.join(plan.characters[:8])}")
            if plan.key_events:
                block.append(f"  关键事件：{'；'.join(plan.key_events[:4])}")
            if plan.foreshadowing:
                block.append(f"  伏笔：{'；'.join(plan.foreshadowing[:3])}")

        # 只展示有实质内容的章节
        if len(block) > 1:
            lines.append("\n".join(block))

    return "\n\n".join(lines) if lines else ""


def _collect_following_new_entities(project, vol_idx, ch_idx, count=5):
    """
    收集后续 N 章规划中出现、但尚未建档的实体。
    覆盖角色与怪物两类（其余类型后续章节规划通常不直接涉及）。
    返回 list[{"type", "name", "first_appear_in"}]
    """
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

    known_chars = {c.name for c in project.characters}
    known_monsters = {m.name for m in project.monsters}
    known_aliases = set()
    for c in project.characters:
        for a in c.aliases or []:
            known_aliases.add(a)
    for m in project.monsters:
        for a in m.aliases or []:
            known_aliases.add(a)

    following = flat[cur_pos + 1: cur_pos + 1 + count]
    result = []
    seen = set()

    def _add(entity_type, name, vi, ci):
        name = (name or "").strip()
        if not name:
            return
        if entity_type == "character":
            if name in known_chars or name in known_aliases:
                return
        elif entity_type == "monster":
            if name in known_monsters or name in known_aliases:
                return
        key = (entity_type, name)
        if key in seen:
            return
        seen.add(key)
        result.append({
            "type": entity_type,
            "name": name,
            "first_appear_in": f"第{vi + 1}卷 第{ci + 1}章",
        })

    for vi, ci, ch in following:
        plan = getattr(ch, "plan", None)
        if not plan:
            continue

        # 角色：从 plan.characters 提取
        for name in plan.characters or []:
            _add("character", name, vi, ci)

        # 怪物：从 required_entities.monsters（若有细纲）+ key_events 文本匹配
        req = plan.required_entities or {}
        for name in req.get("monsters") or []:
            _add("monster", name, vi, ci)

        # 兜底：扫描 key_events 中是否出现"未建档怪物"（名称需为已建档怪物才能匹配）
        # 此处不扫描，因为未建档怪物名称无法可靠识别。

    return result


# ============================================================
# 解析与应用
# ============================================================

def parse_detailed_outline_response(text):
    """解析 AI 返回，返回 dict 或抛异常"""
    if not text:
        raise ValueError("AI 返回为空")
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
        raise ValueError("解析结果不是 JSON 对象")

    detailed_outline = [
        str(x).strip() for x in (data.get("detailed_outline") or [])
        if str(x).strip()
    ]
    if not detailed_outline:
        raise ValueError("细纲为空")

    re_dict = data.get("required_entities") or {}
    required_entities = {
        "characters": [
            str(x).strip() for x in (re_dict.get("characters") or [])
            if str(x).strip()
        ],
        "monsters": [  # 新增
            str(x).strip() for x in (re_dict.get("monsters") or [])
            if str(x).strip()
        ],
        "locations": [
            str(x).strip() for x in (re_dict.get("locations") or [])
            if str(x).strip()
        ],
        "items": [
            str(x).strip() for x in (re_dict.get("items") or [])
            if str(x).strip()
        ],
        "organizations": [
            str(x).strip() for x in (re_dict.get("organizations") or [])
            if str(x).strip()
        ],
        "new_entities": [
            e for e in (re_dict.get("new_entities") or [])
            if isinstance(e, dict)
        ],
    }

    return {
        "thought": (data.get("_thought") or "").strip(),
        "detailed_outline": detailed_outline,
        "required_entities": required_entities,
        "transition_notes": (data.get("transition_notes") or "").strip(),
    }


def apply_detailed_outline(project, vol_idx, ch_idx, result):
    """把细纲结果写入 chapter.plan"""
    ch = project.volumes[vol_idx].chapters[ch_idx]
    if not ch.plan:
        ch.plan = ChapterPlan(title=ch.title)
    ch.plan.detailed_outline = result["detailed_outline"]
    ch.plan.required_entities = result["required_entities"]
    ch.plan.transition_notes = result["transition_notes"]
    ch.plan.outline_thought = result["thought"]