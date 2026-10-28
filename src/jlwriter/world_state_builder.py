"""
世界状态生成：从上一版 L0 + 当前章正文，用 LLM 提取本版 L0
"""
from .models import WorldState, CharacterState


def get_previous_world_state(project, vol_idx, ch_idx):
    """
    返回"章号 < (vol_idx, ch_idx)"的最新 WorldState。
    若没有历史 L0，返回 None。
    """
    target_key = (vol_idx, ch_idx)
    candidates = [
        ws for ws in project.world_states
        if (ws.up_to_volume, ws.up_to_chapter) < target_key
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda ws: (ws.up_to_volume, ws.up_to_chapter))


def get_world_state_at(project, vol_idx, ch_idx):
    """返回与 (vol_idx, ch_idx) 精确匹配的 WorldState，不存在则 None"""
    for ws in project.world_states:
        if ws.up_to_volume == vol_idx and ws.up_to_chapter == ch_idx:
            return ws
    return None


def save_world_state(project, state: WorldState):
    """写入 project.world_states，同章号覆盖"""
    for i, ws in enumerate(project.world_states):
        if (ws.up_to_volume == state.up_to_volume
                and ws.up_to_chapter == state.up_to_chapter):
            project.world_states[i] = state
            return
    project.world_states.append(state)
    project.world_states.sort(
        key=lambda ws: (ws.up_to_volume, ws.up_to_chapter)
    )


# ============================================================
# Prompt 构建
# ============================================================

def build_world_state_prompt(project, vol_idx, ch_idx,
                             previous_state, chapter_content,
                             chapter_summary=""):
    """构建 L0 生成 prompt"""
    vol = project.volumes[vol_idx]
    ch = vol.chapters[ch_idx]

    # 上一版 L0 文本
    if previous_state:
        prev_text = _format_world_state(previous_state)
    else:
        prev_text = "（无，这是本书第一章）"

    # 角色名单（供 LLM 参考，避免遗漏或误引入）
    character_names = [c.name for c in project.characters if c.name]
    char_hint = "、".join(character_names[:30]) if character_names else "（暂无）"

    content = (chapter_content or "").strip()
    if len(content) > 15000:
        content = content[:15000] + f"\n……（已截断，原文字数 {len(chapter_content)}）"

    summary_block = ""
    if chapter_summary and chapter_summary.strip():
        summary_block = f"\n【本章大纲】\n{chapter_summary.strip()}\n"

    prompt = f"""你是小说状态管理员。请根据下面这一章的正文，更新"截至本章末尾的世界状态"。

##上一版世界状态
{prev_text}

##本章正文
第{vol_idx + 1}卷《{vol.title}》 第{ch_idx + 1}章《{ch.title}》
{summary_block}
{content}

##提取任务
基于【上一版世界状态】和【本章正文】，输出"截至本章末尾"的新版世界状态。
只需描述"当前"状态，精简，不记录流水账。

##提取规则
1. 只提取本章正文中明确出现的信息，不编造
2. 角色状态：只保留本章出场或被明确提及的角色，【本章未被提及角色需删除，也不纳入情节上明显只会登场一次的角色】
   - location：本章末尾角色所在位置，包含多层级地图，如：（顶层）明烛基地->（中层）影环->（下层）报名处
   - physical：健康/受伤/虚弱/中毒/昏迷/死亡（若死亡，必须明确标注）
   - power_level：修为或能力等级（若提及，否则保持原状）
   - emotion：显著的情感状态（可选）
   - known_secrets：截至本章末尾该角色已知的重要秘密
   - current_goal：该角色当前的目标或意图
3. organization_states：本章有变化或明确提及的组织，不删除，只修改或新增
   - name / status（活跃/受创/解散等）/ active_members（当前活跃成员）
4. item_locations：本章有变化或明确提及的重要物品
   - name / holder（当前持有者）/ status（完好/损坏/遗失）
5. active_threads：截至本章末尾仍未收束的情节线
   - 上一版未收束且本章未解决的必须保留
   - 本章新产生的未解之谜加入
   - 本章已解决的移除
6. story_time：本章末尾的故事内时间（如"三日后""当夜子时"）
7. current_location：末尾主视角所在的位置

##候选角色（用于参考，不必全部列出，只列本章出场或被提及者）
{char_hint}

##输出严格 JSON（不要 markdown，不要额外说明）：
{{
  "_thought": "简要说明，80字以内",
  "story_time": "故事内时间",
  "current_location": "主视角位置",
  "character_states": [
    {{
      "name": "角色名",
      "location": "当前位置",
      "physical": "健康/受伤/死亡等",
      "power_level": "修为等级",
      "emotion": "情感状态",
      "known_secrets": ["已知的秘密"],
      "current_goal": "当前目标"
    }}
  ],
  "organization_states": [
    {{
      "name": "组织名",
      "status": "活跃/受创/解散",
      "active_members": ["成员名"]
    }}
  ],
  "item_locations": [
    {{
      "name": "物品名",
      "holder": "持有者",
      "status": "完好/损坏/遗失"
    }}
  ],
  "active_threads": ["未收束的情节线"]
}}

只输出 JSON 对象。"""
    return prompt


def parse_world_state_response(text, vol_idx, ch_idx):
    """解析 AI 返回并组装 WorldState"""
    import json
    try:
        import json_repair
        HAS_JSON_REPAIR = True
    except ImportError:
        HAS_JSON_REPAIR = False

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

    state = WorldState(
        up_to_volume=vol_idx,
        up_to_chapter=ch_idx,
        story_time=(data.get("story_time") or "").strip(),
        current_location=(data.get("current_location") or "").strip(),
    )

    for c in data.get("character_states", []) or []:
        if not isinstance(c, dict):
            continue
        name = (c.get("name") or "").strip()
        if not name:
            continue
        state.character_states.append(CharacterState(
            name=name,
            location=(c.get("location") or "").strip(),
            physical=(c.get("physical") or "").strip(),
            power_level=(c.get("power_level") or "").strip(),
            emotion=(c.get("emotion") or "").strip(),
            known_secrets=[
                str(x).strip() for x in (c.get("known_secrets") or [])
                if str(x).strip()
            ],
            current_goal=(c.get("current_goal") or "").strip(),
        ))

    for o in data.get("organization_states", []) or []:
        if not isinstance(o, dict):
            continue
        name = (o.get("name") or "").strip()
        if not name:
            continue
        state.organization_states.append({
            "name": name,
            "status": (o.get("status") or "").strip(),
            "active_members": [
                str(x).strip() for x in (o.get("active_members") or [])
                if str(x).strip()
            ],
        })

    for i in data.get("item_locations", []) or []:
        if not isinstance(i, dict):
            continue
        name = (i.get("name") or "").strip()
        if not name:
            continue
        state.item_locations.append({
            "name": name,
            "holder": (i.get("holder") or "").strip(),
            "status": (i.get("status") or "").strip(),
        })

    state.active_threads = [
        str(x).strip() for x in (data.get("active_threads") or [])
        if str(x).strip()
    ]

    return state


# ============================================================
# 格式化
# ============================================================

def _format_world_state(ws: WorldState) -> str:
    if not ws:
        return "（无）"
    lines = []
    if ws.story_time:
        lines.append(f"故事时间：{ws.story_time}")
    if ws.current_location:
        lines.append(f"当前位置：{ws.current_location}")

    if ws.character_states:
        lines.append("角色状态：")
        for c in ws.character_states:
            parts = [c.name]
            if c.location:
                parts.append(f"位置={c.location}")
            if c.physical:
                parts.append(f"状态={c.physical}")
            if c.power_level:
                parts.append(f"修为={c.power_level}")
            if c.emotion:
                parts.append(f"情感={c.emotion}")
            if c.current_goal:
                parts.append(f"目标={c.current_goal}")
            if c.known_secrets:
                parts.append(f"已知={'；'.join(c.known_secrets[:3])}")
            lines.append("  - " + "｜".join(parts))

    if ws.organization_states:
        lines.append("组织状态：")
        for o in ws.organization_states:
            parts = [o.get("name", "")]
            if o.get("status"):
                parts.append(f"状态={o['status']}")
            if o.get("active_members"):
                parts.append(f"成员={'、'.join(o['active_members'][:5])}")
            lines.append("  - " + "｜".join(parts))

    if ws.item_locations:
        lines.append("物品位置：")
        for i in ws.item_locations:
            parts = [i.get("name", "")]
            if i.get("holder"):
                parts.append(f"持有={i['holder']}")
            if i.get("status"):
                parts.append(f"状态={i['status']}")
            lines.append("  - " + "｜".join(parts))

    if ws.active_threads:
        lines.append("未收束情节线：")
        for t in ws.active_threads:
            lines.append(f"  - {t}")

    return "\n".join(lines) if lines else "（空状态）"


def format_world_state_for_display(ws: WorldState) -> str:
    """用于 UI 展示的多行文本"""
    header = f"━━━ 世界状态（截至第{ws.up_to_volume + 1}卷 第{ws.up_to_chapter + 1}章）━━━"
    return header + "\n" + _format_world_state(ws)