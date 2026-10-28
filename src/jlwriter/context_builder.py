"""
L1-L4 分层上下文构建器

L1 世界骨架：从 project.skeleton 组装的硬约束
L2 场景实体：本章及前 lookback 章涉及的角色/势力/地点/物品
L3 剧情轨道：前序大纲 + 未回收伏笔 + 本章规划/大纲 + 后序边界
L4 正文上下文：本章已有正文，或上一章完整正文
"""

from .graph_builder import build_graph, is_available as graph_available
from .graph_query import (
    get_multi_subgraph,
    format_subgraph,
)

# ============================================================
# 通用工具
# ============================================================

def _flatten(project):
    """把全书章节拍平为 [(vi, ci, vol, ch)] 线性序列"""
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

# ============================================================
# L0：最新状态
# ============================================================
def build_l0_world_state(project, vol_idx, ch_idx):
    """
    L0 世界状态（截至上一章）。
    阶段暂不接入上下文，仅提供函数供后续启用。
    """
    from .world_state_builder import get_previous_world_state
    prev = get_previous_world_state(project, vol_idx, ch_idx)
    if not prev:
        return ""
    # 若全空则不展示
    if not (prev.story_time or prev.current_location
            or prev.character_states or prev.organization_states
            or prev.item_locations or prev.active_threads):
        return ""
    return "##L0 · 故事当前状态（截至上一章）\n" + _format_world_state_body(prev)


def _format_world_state_body(ws):
    lines = []
    if ws.story_time:
        lines.append(f"故事时间：{ws.story_time}")
    if ws.current_location:
        lines.append(f"当前位置：{ws.current_location}")

    for c in ws.character_states:
        parts = [c.name]
        if c.location:
            parts.append(f"位置={c.location}")
        if c.physical:
            parts.append(f"状态={c.physical}")
        if c.power_level:
            parts.append(f"修为={c.power_level}")
        if c.current_goal:
            parts.append(f"目标={c.current_goal}")
        if c.known_secrets:
            parts.append(f"已知={'；'.join(c.known_secrets[:3])}")
        lines.append("  · " + "｜".join(parts))

    for o in ws.organization_states:
        lines.append(f"  · {o.get('name', '')}（{o.get('status', '')}）")

    for i in ws.item_locations:
        lines.append(
            f"  · {i.get('name', '')}：持有={i.get('holder', '')}"
        )

    if ws.active_threads:
        lines.append("未收束情节线：")
        for t in ws.active_threads:
            lines.append(f"  - {t}")

    return "\n".join(lines)


# ============================================================
# L1：世界骨架 + 世界规则（完整）
# ============================================================

def _first_sentence(text: str, max_len: int = 60) -> str:
    """取一段文本的第一句话或前 N 个字符，用于势力总览的一句话描述"""
    if not text:
        return ""
    text = text.strip()
    for sep in ("。", "！", "？", "；", "\n"):
        idx = text.find(sep)
        if 0 <= idx <= max_len:
            return text[:idx + 1]
    return text[:max_len]


def build_l1_world(project, include_outline:bool=False) -> str:
    """
    L1 · 世界规则（完整）。
    硬规则类字段（核心设定/背景/力量体系/大纲）完整带入，不压缩；
    势力仅给总览（名称 + 性质 + 一句话描述），详细成员与关系由 L2 按需加载。
    """
    parts = []
    has_content = False

    if (project.premise or "").strip():
        has_content = True
        parts.append("### 核心设定")
        parts.append(project.premise.strip())
        parts.append("")

    if (project.story_background or "").strip():
        has_content = True
        parts.append("### 世界背景")
        parts.append(project.story_background.strip())
        parts.append("")

    if (project.power_system or "").strip():
        has_content = True
        parts.append("### 力量体系")
        parts.append(project.power_system.strip())
        parts.append("")

    # 故事总纲：默认不包含
    if include_outline and (project.outline or "").strip():
        has_content = True
        parts.append("### 故事总纲")
        parts.append(project.outline.strip())
        parts.append("")

    # 势力总览：只给名册，详细内容由 L2 提供
    if project.organizations:
        has_content = True
        parts.append("### 势力总览")
        parts.append("（此处仅列出势力名册；涉及具体章节的详细组织信息请见 L2）")
        for o in project.organizations:
            line = f"· {o.name}"
            if o.nature:
                line += f"（{o.nature}）"
            short = _first_sentence(o.description) if o.description else ""
            if short:
                line += f"：{short}"
            parts.append(line)
        parts.append("")

    if not has_content:
        return ""

    header = (
        "##L1 · 世界规则（完整）\n"
        "（以下为完整的硬规则，任何涉及等级/禁忌/背景/主线的续写都必须严格遵守。"
        "这些内容在整个故事中恒定，不随章节变化。"
        "如与后文描述有任何不一致，以此处为准。）"
    )
    return header + "\n" + "\n".join(parts).rstrip()


def _fallback_l1(project) -> str:
    """旧项目或 skeleton 未生成时的降级方案"""
    parts = ["##L1 · 世界骨架（硬约束，不可违背）】"]

    if project.premise:
        parts.append("### 核心矛盾")
        parts.append(project.premise[:1500])

    if project.power_system:
        parts.append("### 力量体系")
        parts.append(project.power_system[:1500])

    if project.organizations:
        parts.append("### 势力格局")
        for o in project.organizations[:10]:
            parts.append(
                f"  · {o.name}（{o.nature}）：{o.description[:120]}"
            )

    if len(parts) == 1:
        return ""   # 无任何可用信息

    return "\n".join(parts)


# ============================================================
# L2：场景相关实体
# ============================================================

def _collect_seed_nodes(project, vol_idx, ch_idx, G, lookback=3):
    """
    收集种子节点：当前章及前 lookback 章出现的实体
    用文本匹配找到种子，交给图遍历做扩展
    """
    if G is None:
        return set()

    flat = _flatten(project)
    pos = _find_pos(flat, vol_idx, ch_idx)
    if pos < 0:
        return set()

    texts = []
    start = max(0, pos - lookback)
    for i in range(start, pos + 1):
        _, _, _, ch = flat[i]
        texts.append(ch.content or "")
        texts.append(ch.summary or "")
        plan = getattr(ch, "plan", None)
        if plan:
            texts.append(plan.to_prompt_text())
    full_text = "\n".join(texts)

    seeds = set()
    for node, data in G.nodes(data=True):
        name = data.get("name", "")
        if not name or len(name) < 2:
            continue
        if name in full_text:
            seeds.add(node)
    return seeds


def build_l2_entities(project, vol_idx, ch_idx):
    """
    L2 场景相关实体：基于图遍历选择
    1. 找种子节点（文本匹配）
    2. 从种子出发做 1 跳扩展
    3. 把子图转为文本
    """
    if not graph_available():
        return _fallback_build_l2(project, vol_idx, ch_idx)

    G = build_graph(project)
    if G is None or G.number_of_nodes() == 0:
        return ""

    seeds = _collect_seed_nodes(project, vol_idx, ch_idx, G, lookback=3)
    if not seeds:
        return ""

    subgraph = get_multi_subgraph(G, seeds, hops=1)
    if subgraph is None or subgraph.number_of_nodes() == 0:
        return ""

    text = format_subgraph(subgraph, max_nodes=60, max_chars=6000)
    if not text:
        return ""

    return "##L2 · 场景相关实体（完整档案）\n" + text


def _fallback_build_l2(project, vol_idx, ch_idx):
    """NetworkX 未安装时的降级方案：纯文本匹配（原有逻辑）"""
    from .character_index import (
        get_characters_mentioned_in_chapter,
        get_locations_mentioned_in_chapter,
        get_organizations_mentioned_in_chapter,
        get_items_mentioned_in_chapter,
    )

    relevant_chars = get_characters_mentioned_in_chapter(
        project, vol_idx, ch_idx
    )
    relevant_locs = get_locations_mentioned_in_chapter(
        project, vol_idx, ch_idx
    )
    relevant_orgs = get_organizations_mentioned_in_chapter(
        project, vol_idx, ch_idx
    )
    relevant_items = get_items_mentioned_in_chapter(
        project, vol_idx, ch_idx
    )

    parts = ["##L2 · 场景相关实体（完整档案）"]
    if relevant_chars:
        parts.append("### 相关角色")
        for c in relevant_chars:
            parts.append(f"  · {c.name}")
            if c.personality:
                parts.append(f"    性格：{c.personality[:120]}")
            if c.habits:
                parts.append(f"    习惯：{c.habits[:80]}")
    if relevant_orgs:
        parts.append("### 相关组织")
        for o in relevant_orgs:
            parts.append(f"  · {o.name}（{o.nature}）：{o.description[:150]}")
    if relevant_locs:
        parts.append("### 相关地点")
        for l in relevant_locs:
            parts.append(f"  · {l.name}（{l.level}）：{l.description[:150]}")
    if relevant_items:
        parts.append("### 相关物品")
        for i in relevant_items:
            parts.append(f"  · {i.name}（{i.type}）：{i.ability[:100]}")

    if len(parts) == 1:
        return ""
    return "\n".join(parts)


# ============================================================
# L3：剧情轨道
# ============================================================

def _collect_active_foreshadowing(project, vol_idx, ch_idx):
    """收集截至当前章仍未回收的伏笔"""
    flat = _flatten(project)
    pos = _find_pos(flat, vol_idx, ch_idx)
    if pos < 0:
        return []

    active = []
    # 1. 已生成章节中的 plan.foreshadowing
    for i in range(pos):
        _, _, _, ch = flat[i]
        plan = getattr(ch, "plan", None)
        if plan:
            for fs in plan.foreshadowing or []:
                if fs and fs not in active:
                    active.append(fs)

    # 2. 弧级伏笔
    for vi, vol in enumerate(project.volumes):
        for arc in vol.arcs:
            for fs in arc.foreshadowing_to_plant or []:
                if fs and fs not in active:
                    active.append(fs)
            for fs in arc.foreshadowing_to_payoff or []:
                if fs in active:
                    active.remove(fs)

    return active


def build_l3_track(project, vol_idx, ch_idx, flat, pos) -> str:
    parts = ["##L3 · 剧情轨道"]

    # 前序章节大纲
    prev_slice = flat[max(0, pos - 5):pos]
    prev_with_summary = [x for x in prev_slice if x[3].summary.strip()]
    if prev_with_summary:
        parts.append("### 前序章节大纲（仅作前情参考，本章不重复）")
        for vi, ci, vol, ch in prev_with_summary:
            parts.append(
                f"  第{vi + 1}卷 第{ci + 1}章《{ch.title}》：{ch.summary.strip()[:300]}"
            )

    # 未回收伏笔
    active_fs = _collect_active_foreshadowing(project, vol_idx, ch_idx)
    if active_fs:
        parts.append("### 未回收伏笔（如遇合适节点可回收）")
        for fs in active_fs:
            parts.append(f"  · {fs}")

    # 当前章节
    _, _, cur_vol, cur_ch = flat[pos]
    plan = getattr(cur_ch, "plan", None)
    if plan:
        parts.append("### 本章规划（必须严格按此推进，不得超前或遗漏）")
        parts.append(plan.to_prompt_text())
        pref = (plan.chapter_preference or "").strip()
        if pref:
            parts.append(
                f"本章偏好侧重：{pref}"
                f"（正文的描写资源应向该方向倾斜，"
                f"其它元素服务于该侧重，不得喧宾夺主）"
            )

    if cur_ch.summary.strip():
        parts.append("### 本章大纲")
        parts.append(cur_ch.summary.strip())

    # 后序边界
    if pos + 1 < len(flat):
        _, _, _, nch = flat[pos + 1]
        parts.append("### 后序边界（本章不得越过以下节点）")
        nplan = getattr(nch, "plan", None)
        if nplan and nplan.goal:
            parts.append(f"  下一章目标：{nplan.goal}")
        if nplan and nplan.key_events:
            parts.append(f"  下一章关键事件：{'；'.join(nplan.key_events[:3])}")
        if nch.summary.strip():
            parts.append(f"  下一章大纲：{nch.summary.strip()[:150]}")

    return "\n".join(parts)


# ============================================================
# L4：正文上下文
# ============================================================

def build_l4_content(flat, pos, max_prev_chars=12000) -> str:
    parts = ["##L4 · 正文上下文"]
    _, _, _, cur_ch = flat[pos]
    content = (cur_ch.content or "").strip()

    if content:
        parts.append("### 本章已有正文（从末尾续写，不要复述已写内容）")
        parts.append(content)
    elif pos > 0:
        _, _, _, pch = flat[pos - 1]
        prev_content = (pch.content or "").strip()
        if prev_content:
            if len(prev_content) > max_prev_chars:
                prev_content = prev_content[-max_prev_chars:]
                parts.append(
                    f"### 上一章正文（原文过长，仅保留最后 {max_prev_chars} 字，"
                    "本章须以此为续写起点）"
                )
            else:
                parts.append("### 上一章完整正文（本章尚未开始，以此为续写起点）")
            parts.append(prev_content)
        else:
            parts.append("###（本章与上一章均无正文，请基于大纲与规划开始写作）")
    else:
        parts.append("### （全书第一章，尚无前文，请基于大纲与规划开始写作）")

    return "\n".join(parts)


# ============================================================
# 组装入口
# ============================================================

def build_context(project, vol_idx, ch_idx,
                  include_l1_rules=True, include_l0=False,
                  include_l1_outline=False) -> str:
    """
    按 L1 → L0 → L2 → L3 → L4 顺序组装完整上下文。
    - L1：世界规则（完整，硬约束）
    - L0：故事当前状态（可选，仅在启用且有快照时插入）
    - L2：场景相关实体（按需筛选）
    - L3：剧情轨道
    - L4：正文上下文
    """
    flat = _flatten(project)
    pos = _find_pos(flat, vol_idx, ch_idx)
    if pos < 0:
        return ""

    sections = []

    if include_l1_rules:
        l1 = build_l1_world(project, include_outline=include_l1_outline)
        if l1:
            sections.append(l1)

    if include_l0:
        l0 = build_l0_world_state(project, vol_idx, ch_idx)
        if l0:
            sections.append(l0)

    l2 = build_l2_entities(project, vol_idx, ch_idx)
    if l2:
        sections.append(l2)

    l3 = build_l3_track(project, vol_idx, ch_idx, flat, pos)
    if l3:
        sections.append(l3)

    l4 = build_l4_content(flat, pos)
    if l4:
        sections.append(l4)

    return "\n\n".join(sections)