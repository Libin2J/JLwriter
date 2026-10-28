"""
Planner Agent：分阶段生成完整的世界观设定
每阶段一次 LLM 调用，带 ReAct 思考字段，可暂停 / 恢复
"""
import json
from dataclasses import dataclass
from typing import List, Dict, Any, Optional
from .key_facts import stringify_parsed

try:
    import json_repair
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False


PLANNER_STAGES = [
    {"id": "premise",       "label": "#核心矛盾", "required": True,
     "description": "故事的核心冲突与主线张力"},
    {"id": "background",    "label": "#故事背景", "required": True,
     "description": "时代、世界、氛围、社会环境"},
    {"id": "power_system",  "label": "#力量体系", "required": False,
     "description": "修炼 / 魔法 / 科技等力量体系"},
    {"id": "outline",       "label": "#故事总纲", "required": True,
     "description": "分卷结构与各卷发展脉络"},
    {"id": "characters",    "label": "#关键人物", "required": True,
     "description": "主角、配角、反派等关键角色"},
    {"id": "organizations", "label": "#主要势力", "required": False,
     "description": "门派、家族、王国、组织等"},
    {"id": "locations",     "label": "#地图与地点", "required": False,
     "description": "大陆 / 国家 / 城市 / 城区 / 建筑 / 秘境等"},
    {"id": "items",         "label": "#重要物品", "required": False,
     "description": "神器、法宝、关键道具"},
    {"id": "monsters",      "label": "怪物设计", "required": False,
     "description": "妖兽、魔物、异种等怪物设定"},
]


@dataclass
class PlannerPreset:
    genre: str = ""
    theme: str = ""
    tone: str = ""
    target_length: str = ""
    volume_count: int = 0
    need_power_system: bool = False
    need_organizations: bool = False
    need_locations: bool = False
    need_items: bool = False
    need_monsters: bool = False  # 新增
    user_notes: str = ""


class PlannerSession:
    """维护跨阶段状态，支持单阶段重生成"""

    def __init__(self, preset: PlannerPreset):
        self.preset = preset
        self.stage_results: Dict[str, Any] = {}
        self.completed_stages: List[str] = []
        self.failed_stages: List[str] = []
        self.key_facts_registry: Dict[str, dict] = {}  # 新增

    def get_active_stages(self) -> List[dict]:
        stages = []
        for stage in PLANNER_STAGES:
            sid = stage["id"]
            if stage["required"]:
                stages.append(stage)
            elif sid == "power_system" and self.preset.need_power_system:
                stages.append(stage)
            elif sid == "organizations" and self.preset.need_organizations:
                stages.append(stage)
            elif sid == "locations" and self.preset.need_locations:
                stages.append(stage)
            elif sid == "items" and self.preset.need_items:
                stages.append(stage)
            elif sid == "monsters" and self.preset.need_monsters:  # 新增
                stages.append(stage)
        return stages

    def next_stage(self) -> Optional[dict]:
        for stage in self.get_active_stages():
            if stage["id"] not in self.completed_stages:
                return stage
        return None

    def mark_complete(self, stage_id: str, result: Any, key_facts: dict = None):
        self.stage_results[stage_id] = result
        if stage_id not in self.completed_stages:
            self.completed_stages.append(stage_id)
        if stage_id in self.failed_stages:
            self.failed_stages.remove(stage_id)
        if key_facts:
            self.key_facts_registry[stage_id] = key_facts

    def mark_failed(self, stage_id: str):
        if stage_id not in self.failed_stages:
            self.failed_stages.append(stage_id)

    def is_all_done(self) -> bool:
        return self.next_stage() is None

    def build_context_summary(self, max_chars: int = 4000) -> str:
        if not self.stage_results:
            return "（这是第一阶段，尚无已有内容）"
        parts = []
        for stage in PLANNER_STAGES:
            sid = stage["id"]
            if sid not in self.stage_results:
                continue
            result = self.stage_results[sid]
            parts.append(f"【已完成的{stage['label']}】")
            if isinstance(result, str):
                parts.append(result)
            elif isinstance(result, list):
                for item in result:
                    if isinstance(item, dict):
                        name = item.get("name", "")
                        desc = item.get("description", "") or item.get("personality", "")
                        parts.append(f"- {name}: {str(desc)}")
                    else:
                        parts.append(f"- {str(item)}")
            elif isinstance(result, dict):
                for k, v in result.items():
                    if k.startswith("_"):
                        continue
                    parts.append(f"- {k}: {str(v)}")
            parts.append("")
        text = "\n".join(parts)
        # if len(text) > max_chars:
        #     text = text[:max_chars] + "\n……（已截断）"
        return text


# ---------- Prompt 构建 ----------
def build_golden_three_hint(context="outline") -> str:
    """
    返回黄金三章提示文本。
    context 取值：
        outline           - 故事总纲生成阶段
        arc               - 故事弧拆解阶段
        chapters          - 章节规划生成阶段
        detailed_outline  - 细纲展开阶段
    """
    base = (
        "##黄金三章设计原则（适用于全书第 1-3 章）\n"
        "黄金三章是长篇小说的开篇命门，必须在 3 章内完成以下目标：\n"
        "- 第 1 章：抓住读者。开场 500 字内建立主角、场景、核心冲突或悬念，"
        "让读者产生「接下来会发生什么」的好奇心；结尾留下强钩子\n"
        "- 第 2 章：深化冲突。展开第 1 章的悬念，明确主角的目标与阻碍，"
        "引入关键配角或对立力量；结尾形成「必须往下看」的推力\n"
        "- 第 3 章：第一个小高潮。给出第一个爽点或情感爆发点，"
        "让读者对主角产生情感投入，对后续发展形成期待\n"
    )

    if context == "outline":
        base += (
            "\n构建故事总纲时必须保证：\n"
            "1. 第一卷的前 3 章就是黄金三章，总纲中应明确这三章的核心事件\n"
            "2. 第 1 章的核心冲突/悬念、第 2 章的深化、第 3 章的小高潮，"
            "总纲需给出大致方向\n"
            "3. 第 1 章不得以长篇世界观铺垫开场，必须有具体场景或冲突切入\n"
        )
    elif context == "arc":
        base += (
            "\n拆解第一卷时，弧结构必须满足：\n"
            "1. 第一弧的前 3 章构成黄金三章\n"
            "2. 第一弧的目标应明确包含「在 3 章内让读者建立投入」\n"
            "3. 第一弧的关键转折点至少有一个落在第 3 章（小高潮）\n"
        )
    elif context == "chapters":
        base += (
            "\n本批若涉及全书第 1-3 章，必须按黄金三章原则设计：\n"
            "1. 每章必须有明确的「抓住读者」抓手（悬念/画面/反转/爽点）\n"
            "2. 第 1 章必须在开头快速进入主线冲突，避免拖沓铺垫\n"
            "3. 第 2、3 章节奏紧凑，避免日常或对话灌水\n"
            "4. 前三章的每章结尾钩子必须强烈，环环相扣\n"
            "5. 三章之内让读者建立「我在追一个什么故事」的清晰预期\n"
        )
    elif context == "detailed_outline":
        base += (
            "\n本章若属于全书第 1-3 章，细纲必须遵循黄金三章原则：\n"
            "1. 细纲的第一个节拍必须快速进入场景/冲突，不要长铺垫\n"
            "2. 细纲的最后一个节拍必须是强钩子\n"
            "3. 本章的过渡作用要让位于「抓读者」，节奏优先\n"
            "4. 避免在本章安排与主线无关的日常闲笔\n"
        )

    return base


def build_stage_prompt(session: PlannerSession, stage: dict, enable_golden_three: bool = False) -> str:
    preset = session.preset
    stage_id = stage["id"]

    preset_lines = []
    if preset.genre:
        preset_lines.append(f"题材：{preset.genre}")
    if preset.theme:
        preset_lines.append(f"主题：{preset.theme}")
    if preset.tone:
        preset_lines.append(f"基调：{preset.tone}")
    if preset.target_length:
        preset_lines.append(f"目标长度：{preset.target_length}")
    if preset.volume_count:
        preset_lines.append(f"分卷数：{preset.volume_count}")
    if preset.user_notes:
        preset_lines.append(f"用户补充说明：{preset.user_notes}")
    preset_text = "\n".join(preset_lines) if preset_lines else "（未指定，请自行判断合理设定）"

    context = session.build_context_summary()
    instruction = _get_stage_instruction(stage_id, preset)
    fmt = _get_stage_format(stage_id)

    prompt = f"""你正在为一部新小说构建世界观。##当前阶段：【{stage['label']}】。

##用户预设
{preset_text}

##已完成的前序设定
{context}

##本阶段任务
{instruction}

##工作流程
请先思考，再输出：
1. Thought（思考）：简要分析本阶段应包含哪些要素，如何与前序设定保持一致，100-200 字
2. Output（输出）：严格按下方 JSON 格式输出

##输出格式
{fmt}

##硬性要求
- 只输出 JSON，阶段区块内用markdown三级标题‘###’开始切分、不要额外解释
- 思考内容放在 JSON 的 "_thought" 字段中
- 内容【必须与已完成的前序设定保持设定一致】
- 不要重复描述相同或相似内容，只输出建立在已有内容之上的本阶段的新内容，并且新内容需要避免相同概念/设定的描述
- 所有名称、术语和设定需与前序设定统一，【注意角色年龄与时间跨度的一致性关系】
- 设定与规划必须明确区分，【力量体系需严格保持专业性和精准性，不预设任何故事情节，或者在底部加入'剧情联系'】
- 任何阶段的输出长度都尽量控制在5000字以内
"""
    # 原有 prompt 构造代码保持不变，在 return 前注入
    if enable_golden_three and stage_id == "outline":
        prompt += "\n" + build_golden_three_hint("outline")

    return prompt


def _get_stage_instruction(stage_id: str, preset: PlannerPreset) -> str:
    return {
        "premise": (
            "提炼故事的核心矛盾。包含：\n"
            "- 世界或社会面临的根本问题\n"
            "- 主角的核心目标与主要阻碍\n"
            "- 贯穿全书的主线张力\n"
            "500-800字，精炼有力。"
        ),
        "background": (
            "构建完整的故事背景。包含：\n"
            "- 时代背景（古代 / 现代 / 未来 / 架空）\n"
            "- 世界的基本样貌、社会结构和简要货币体系\n"
            "- 影响故事的关键历史事件\n"
            "- 整体氛围与基调\n"
            "输出长度控制在 5000 字以内。"
        ),
        "power_system": (
            "设计完整的力量体系。包含：\n"
            "- 力量的来源与本质\n"
            "- 等级划分与晋升方式\n"
            "- 获取与提升方式\n"
            "- 可能的限制与代价(可以为空)\n"
            #"- 可能的代表人物或势力\n"
            "输出长度控制在 5000 字以内。"
        ),
        "outline": (
            f"构建故事总纲，分为 {preset.volume_count or '若干'} 卷。\n"
            "- 先构思整本书的篇幅和整体剧情走向以及进度，再根据进度分卷，最后输出大纲内容\n"
            "每卷大纲包含：\n"
            "- 卷名\n"
            "- 该卷的核心事件与冲突故事线，按时间线展开排序\n"
            "- 主角的成长或变化\n"
            "- 结尾的悬念\n"
            "- 本卷计划章节数\n"
            "输出控制在每卷 800-1000 字，以自然段落输出，每生成新卷大纲时，需回顾之前的大纲"
        ),
        "characters": (
            "设计 5-10 位关键角色。每位包含：\n"
            "- 姓名与别名\n"
            "- 外貌特征\n"
            "- 性格特点\n"
            "- 语言与行为习惯\n"
            "- 身份背景\n"
            "- 初始状态：年龄、力量等级、情绪、健康状况\n"
            "- 与其他角色的关系\n"
            "- 在故事中的作用（主角 / 配角 / 反派 / 导师）\n"
            "注：此阶段只建立角色之间的关系，角色与其他实体的关联由后续阶段反向建立。"
        ),
        "organizations": (
            "设计 3-6 个主要势力。每个包含：\n"
            "- 名称\n"
            "- 性质（宗教、家族、王国、公司、社团、行政机构、军事机构、统治者等）\n"
            "- 核心理念与目标\n"
            "- 主要成员（引用【关键人物】阶段已生成的角色名，多个用数组）\n"
            "- 与其他势力的关系（relations，引用本次生成的其他势力名）\n"
            "系统会自动根据 members 建立角色→组织的所属关系，"
            "根据 relations 建立组织↔组织的关系。"
        ),
        "locations": (
            "设计 5-10 个重要地点。每个包含：\n"
            "- 名称\n"
            "- 层级（大陆 / 国家 / 城市 / 城区 / 建筑 / 秘境）\n"
            "- 上级地点（parent，填写父级地点名，可留空）\n"
            "- 管辖势力（governing_organization，引用【主要势力】已生成的组织名，可留空）\n"
            "- 地理、氛围、特色描述\n"
            "系统会根据 parent 建立地点→地点的隶属于关系，"
            "根据 governing_organization 建立组织→地点的辖区关系。"
        ),
        "items": (
            "设计 3-6 件重要物品。每件包含：\n"
            "- 名称\n"
            "- 类型（神器 / 法宝 / 道具 / 武器）\n"
            "- 描述\n"
            "- 功能或特殊能力\n"
            "- 归属者（owner，引用已生成的角色名或组织名，可留空）\n"
            "系统会根据 owner 建立 owner→物品的拥有关系。"
        ),
        "monsters": (
            "设计 3-8 种重要怪物，供主角在故事中遭遇。每种包含：\n"
            "- 名称\n"
            "- 别名（如流传于民间的俗称，可留空）\n"
            "- 外形（体型、颜色、显著特征，50-120 字）\n"
            "- 行为与能力（习性、战斗方式、特殊能力或危险点、对应的力量体系等级，80-200 字）\n"
            "- 纲目（可选，如：妖兽-蛇形-黑鳞蛟科，用于分类）\n"
            "要求：\n"
            "1. 怪物应与世界的背景、力量体系、地理环境相匹配\n"
            "2. 怪物应有强弱梯度，不可全部是同一强度\n"
            "3. 怪物不能仅作为「战斗靶子」，最好与剧情、势力、地点有关联\n"
            "4. 避免与角色功能重叠（怪物不是角色）"
        ),
    }.get(stage_id, "请生成该阶段的内容。")


def _get_stage_format(stage_id: str) -> str:
    return {
        "premise": '{\n  "_thought": "思考内容，200字以内",\n  "premise": "核心矛盾完整描述"\n}',
        "background": '{\n  "_thought": "思考内容，200字以内",\n  "story_background": "完整故事背景, 5000字以内"\n}',
        "power_system": '{\n  "_thought": "思考内容，200字以内",\n  "power_system": "完整力量体系, 5000字以内"\n}',
        "outline": '{\n  "_thought": "思考内容，200字以内",\n  "outline": "故事总纲完整文本, 5000字以内"\n}',
        "characters": '''{
  "_thought": "思考内容",
  "characters": [
    {
      "name": "角色名",
      "aliases": ["别名"],
      "appearance": "外貌",
      "personality": "性格",
      "habits": "语言与行为习惯",
      "identity": "身份背景",
      "role": "主角/配角/反派/导师",
      "age": "初始年龄（如：18 岁）",
      "power_level": "初始力量等级（如：炼气三层、无）",
      "emotion": "初始情绪（如：对师门充满期待、对生存感到紧迫）",
      "health": "初始健康状况（通常为：健康）",
      "relations": [
        {"to": "另一角色", "type": "关系类型", "description": "关系说明"}
      ]
    }
  ]
}''',
        "organizations": '''{
  "_thought": "思考内容，200字以内",
  "organizations": [
    {
      "name": "势力名",
      "nature": "门派/家族/王国/教团/行政机构/军事机构/统治者等",
      "description": "核心理念与描述",
      "members": ["角色名1", "角色名2"],
      "relations": [
        {"to": "其他势力", "type": "敌对/联盟/中立", "description": "关系说明"}
      ]
    }
  ]
}''',
        "locations": '''{
  "_thought": "思考内容",
  "locations": [
    {
      "name": "地点名",
      "level": "大陆/国家/城市/建筑/秘境",
      "parent": "上级地点（可空）",
      "governing_organization": "管辖势力（可空）",
      "description": "描述"
    }
  ]
}''',
        "items": '''{
  "_thought": "思考内容，200字以内",
  "items": [
    {
      "name": "物品名",
      "type": "神器/法宝/道具",
      "description": "描述",
      "ability": "特殊能力",
      "owner": "归属者"
    }
  ]
}''',
        "monsters": '''{
  "_thought": "思考内容",
  "monsters": [
    {
      "name": "怪物名",
      "aliases": ["别名1"],
      "appearance": "外形描述",
      "behavior_ability": "行为与能力描述",
      "category": "妖兽-蛇形-黑鳞蛟科"
    }
  ]
}''',
    }.get(stage_id, '{"_thought": "...", "content": "..."}')


def parse_stage_response(text: str) -> dict:
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
        return json.loads(json_str)
    except json.JSONDecodeError:
        if HAS_JSON_REPAIR:
            return json_repair.loads(json_str)
        raise


def build_stage_optimize_prompt(session: PlannerSession, stage: dict,
                                current_content: str,
                                guidance: str,
                                enable_golden_three: bool = False) -> str:
    """
    基于现有内容优化某阶段。

    current_content: UI 上该阶段当前的文本（TEXT_STAGES 为纯文本，其它为 JSON 文本）
    guidance: 用户填写的优化指引
    """
    stage_id = stage["id"]
    base_prompt = build_stage_prompt(
        session, stage, enable_golden_three=enable_golden_three
    )

    parts = []
    parts.append(base_prompt)
    parts.append("")
    parts.append("=" * 10)
    parts.append("#本阶段已有内容（需在保留其合理部分的基础上优化）")
    parts.append(current_content.strip() or "（空）")
    parts.append("")
    parts.append("#用户优化指令")
    parts.append(guidance.strip())
    parts.append("")
    parts.append("#优化要求")
    parts.append("- 在【本阶段已有内容】基础上改进，不要完全重写")
    parts.append("- 严格按照【用户优化指引】进行调整")
    parts.append("- 除非客户要求，否则尽可能保留已有内容中合理的部分（人物、术语、核心设定），首要保证阶段整体逻辑自洽")
    parts.append("- 确保修改后内容与【已完成的前序设定】的统一性")
    parts.append("- 输出仍为原要求的 JSON 格式，不要添加解释")
    parts.append("")
    parts.append("请输出优化后的完整 JSON：")

    return "\n".join(parts)

# ---------- 写入项目 ----------

def _add_relation(project, from_ep, to_ep, rel_type, description="", chapter=None):
    """统一写入关系：按 (from, to, type) 去重，描述追加"""
    if not from_ep or not to_ep or from_ep == to_ep:
        return
    for r in project.relations:
        if (r.get("from") == from_ep
                and r.get("to") == to_ep
                and r.get("type") == rel_type):
            old = (r.get("description") or "").strip()
            if description and description not in old:
                r["description"] = (
                    f"{old}；{description}".strip("；") if old else description
                )
            return
    project.relations.append({
        "from": from_ep,
        "to": to_ep,
        "type": rel_type,
        "description": description,
        "chapter": chapter,
    })

def merge_planner_results_into_project(project, session: PlannerSession):
    """
    将 PlannerSession 结果写入项目。
    - 标量字段（premise / story_background / power_system / outline）直接覆盖
    - 列表字段（characters / organizations / locations / items）合并去重
    - relations 追加去重
    返回统计信息 dict
    """
    from .models import (
        CharacterProfile,
        Location,
        Organization,
        Item,
    )

    stats = {"characters": 0, "organizations": 0, "locations": 0,
             "items": 0, "monsters": 0, "relations": 0}

    # 标量字段
    if "premise" in session.stage_results:
        r = session.stage_results["premise"]
        if isinstance(r, dict) and r.get("premise"):
            project.premise = r["premise"]
    if "background" in session.stage_results:
        r = session.stage_results["background"]
        if isinstance(r, dict) and r.get("story_background"):
            project.story_background = r["story_background"]
    if "power_system" in session.stage_results:
        r = session.stage_results["power_system"]
        if isinstance(r, dict) and r.get("power_system"):
            project.power_system = r["power_system"]
    if "outline" in session.stage_results:
        r = session.stage_results["outline"]
        if isinstance(r, dict) and r.get("outline"):
            project.outline = r["outline"]

    # 角色
    if "characters" in session.stage_results:
        r = session.stage_results["characters"]
        chars = r.get("characters", []) if isinstance(r, dict) else []
        for c in chars:
            name = (c.get("name") or "").strip()
            if not name:
                continue
            existing = next(
                (x for x in project.characters if x.name == name), None
            )
            if existing is None:
                existing = CharacterProfile(name=name)
                project.characters.append(existing)
                stats["characters"] += 1
            for fld, key in [
                ("appearance", "appearance"),
                ("personality", "personality"),
                ("habits", "habits"),
            ]:
                val = (c.get(key) or "").strip()
                if val and not getattr(existing, fld):
                    setattr(existing, fld, val)
            # 初始状态
            for fld, key in [
                ("age", "age"),
                ("power_level", "power_level"),
                ("emotion", "emotion"),
                ("health", "health"),
                ("status_notes", "status_notes"),
            ]:
                val = (c.get(key) or "").strip()
                if val and not getattr(existing, fld, ""):
                    setattr(existing, fld, val)
            # 身份并入 personality（若无更合适字段）
            identity = (c.get("identity") or "").strip()
            if identity and identity not in existing.personality:
                existing.personality = (
                    f"{existing.personality}；身份：{identity}"
                    if existing.personality else f"身份：{identity}"
                )
            for a in c.get("aliases", []) or []:
                a = str(a).strip()
                if a and a != name and a not in existing.aliases:
                    existing.aliases.append(a)
            # 关系（角色 ↔ 角色）
            from .models import format_endpoint
            a_ep = format_endpoint("character", name)
            for rel in c.get("relations", []) or []:
                to_name = (rel.get("to") or "").strip()
                if not to_name:
                    continue
                typ = (rel.get("type") or "关系").strip()
                desc = (rel.get("description") or "").strip()
                b_ep = format_endpoint("character", to_name)
                _add_relation(project, a_ep, b_ep, typ, desc)
                stats["relations"] += 1

    # 势力
    if "organizations" in session.stage_results:
        from .models import format_endpoint
        r = session.stage_results["organizations"]
        orgs = r.get("organizations", []) if isinstance(r, dict) else []
        for o in orgs:
            name = (o.get("name") or "").strip()
            if not name:
                continue
            existing = next(
                (x for x in project.organizations if x.name == name), None
            )
            if existing is None:
                existing = Organization(name=name)
                project.organizations.append(existing)
                stats["organizations"] += 1
            existing.nature = (o.get("nature") or "").strip() or existing.nature
            existing.description = (
                    (o.get("description") or "").strip() or existing.description
            )

            # 成员 → 建立 角色→组织 的所属关系
            for m in o.get("members", []) or []:
                m = str(m).strip()
                if not m:
                    continue
                if m not in existing.members:
                    existing.members.append(m)
                _add_relation(
                    project,
                    format_endpoint("character", m),
                    format_endpoint("organization", name),
                    "所属", "成员",
                )

            # 组织间关系
            for rel in o.get("relations", []) or []:
                to_org = (rel.get("to") or "").strip()
                if not to_org:
                    continue
                typ = (rel.get("type") or "关系").strip()
                desc = (rel.get("description") or "").strip()
                existing.relations.append({
                    "to": to_org, "type": typ, "description": desc,
                })
                _add_relation(
                    project,
                    format_endpoint("organization", name),
                    format_endpoint("organization", to_org),
                    typ, desc,
                )

    # 地点
    if "locations" in session.stage_results:
        from .models import format_endpoint
        r = session.stage_results["locations"]
        locs = r.get("locations", []) if isinstance(r, dict) else []
        for l in locs:
            name = (l.get("name") or "").strip()
            if not name:
                continue
            existing = next(
                (x for x in project.locations if x.name == name), None
            )
            if existing is None:
                existing = Location(name=name)
                project.locations.append(existing)
                stats["locations"] += 1
            existing.level = (l.get("level") or "").strip() or existing.level
            existing.parent = (l.get("parent") or "").strip() or existing.parent
            existing.description = (
                    (l.get("description") or "").strip() or existing.description
            )

            # 上级地点 → location→location（隶属于）
            if existing.parent:
                _add_relation(
                    project,
                    format_endpoint("location", name),
                    format_endpoint("location", existing.parent),
                    "隶属于",
                )

            # 管辖势力 → organization→location（辖区）
            gov = (l.get("governing_organization") or "").strip()
            if gov:
                _add_relation(
                    project,
                    format_endpoint("organization", gov),
                    format_endpoint("location", name),
                    "辖区",
                )

    # 物品
    if "items" in session.stage_results:
        from .models import format_endpoint
        r = session.stage_results["items"]
        items = r.get("items", []) if isinstance(r, dict) else []
        for i in items:
            name = (i.get("name") or "").strip()
            if not name:
                continue
            existing = next(
                (x for x in project.items if x.name == name), None
            )
            if existing is None:
                existing = Item(name=name)
                project.items.append(existing)
                stats["items"] += 1
            existing.type = (i.get("type") or "").strip() or existing.type
            existing.description = (
                    (i.get("description") or "").strip() or existing.description
            )
            existing.ability = (i.get("ability") or "").strip() or existing.ability
            existing.owner = (i.get("owner") or "").strip() or existing.owner

            # owner → 建立 角色/组织 → 物品 的拥有关系
            owner = existing.owner
            if owner:
                owner_ep = None
                if any(c.name == owner for c in project.characters):
                    owner_ep = format_endpoint("character", owner)
                elif any(o.name == owner for o in project.organizations):
                    owner_ep = format_endpoint("organization", owner)
                if owner_ep:
                    _add_relation(
                        project,
                        owner_ep,
                        format_endpoint("item", name),
                        "拥有",
                    )

    # 怪物
    if "monsters" in session.stage_results:
        from .models import Monster
        r = session.stage_results["monsters"]
        monsters = r.get("monsters", []) if isinstance(r, dict) else []
        for m in monsters:
            name = (m.get("name") or "").strip()
            if not name:
                continue
            existing = next(
                (x for x in project.monsters if x.name == name), None
            )
            if existing is None:
                existing = Monster(name=name)
                project.monsters.append(existing)
                stats["monsters"] = stats.get("monsters", 0) + 1

            appearance = (m.get("appearance") or "").strip()
            behavior = (m.get("behavior_ability") or "").strip()
            category = (m.get("category") or "").strip()

            # 只填空：planner 重跑时保留用户后编辑的内容
            if not existing.appearance and appearance:
                existing.appearance = appearance
            if not existing.behavior_ability and behavior:
                existing.behavior_ability = behavior
            if not existing.category and category:
                existing.category = category

            for a in m.get("aliases") or []:
                a = str(a).strip()
                if a and a != existing.name and a not in existing.aliases:
                    existing.aliases.append(a)

    # 自动生成设定集文本（仅保留力量体系与势力；
    # 地点与物品已迁移至故事档案，不再写入设定集）
    settings_parts = []
    if project.power_system:
        settings_parts.append("##力量体系")
        settings_parts.append(project.power_system)
    if project.organizations:
        settings_parts.append("\n##主要势力")
        for o in project.organizations:
            members = "、".join(o.members) if o.members else "—"
            settings_parts.append(
                f"- {o.name}（{o.nature}）：{o.description}｜成员：{members}"
            )
    project.settings_book = "\n".join(settings_parts) if settings_parts else ""

    return stats

# ---------- 分卷识别 ----------

def build_volume_extraction_prompt(project) -> str:
    outline = (project.outline or "").strip()
    if not outline:
        outline = "（故事总纲为空，请根据背景与核心矛盾推演合理的分卷结构）"

    bg = (project.story_background or "").strip()
    prem = (project.premise or "").strip()

    parts = []
    parts.append(f"#上下文\n")
    if prem:
        parts.append(f"##核心矛盾\n{prem}")
    if bg:
        parts.append(f"##故事背景\n{bg}")
    parts.append(f"##故事总纲\n{outline}")

    context = "\n\n".join(parts)

    prompt = f"""你是一位小说策划。请从下面的故事总纲中识别出分卷结构。

{context}

#任务
识别出全书的分卷列表。每个分卷包含：
- title：卷名（如"第一卷 初入宗门"）
- summary：该卷的核心事件、主角变化、与主线的关系、结尾悬念，500-1000 字

要求：
1. 若故事总纲已明确分卷，直接提取
2. 若未明确，根据情节节奏合理划分
3. 每卷内容必须与总纲一致，不得编造
4. 卷数控制在 2-6 卷，若卷数较少，可适当增加summary字段字数

##输出格式
只输出 JSON，不要 markdown 标记或额外说明：
{{
  "_thought": "简要思考，200字以内",
  "volumes": [
    {{"title": "卷名", "summary": "卷摘要，500-1000 字"}}
  ]
}}"""
    return prompt


def parse_volume_response(text: str) -> list:
    data = parse_stage_response(text)
    volumes = data.get("volumes", []) if isinstance(data, dict) else []
    result = []
    for v in volumes:
        if not isinstance(v, dict):
            continue
        title = (v.get("title") or "").strip()
        summary = (v.get("summary") or "").strip()
        if title:
            result.append({"title": title, "summary": summary})
    return result


# ---------- 章节规划 ----------


def parse_chapter_plan_response(text: str) -> list:
    data = parse_stage_response(text)
    chapters = data.get("chapters", []) if isinstance(data, dict) else []
    result = []
    for c in chapters:
        if not isinstance(c, dict):
            continue
        title = (c.get("title") or "").strip()
        if not title:
            continue
        result.append({
            "title": title,
            "goal": (c.get("goal") or "").strip(),
            "characters": [str(x).strip() for x in (c.get("characters") or []) if str(x).strip()],
            "key_events": [str(x).strip() for x in (c.get("key_events") or []) if str(x).strip()],
            "foreshadowing": [str(x).strip() for x in (c.get("foreshadowing") or []) if str(x).strip()],
            "ending_hook": (c.get("ending_hook") or "").strip(),
            "estimated_words": int(c.get("estimated_words", 3000) or 3000),
        })
    return result



# ============================================================
# 规划一致性校验
# ============================================================
def build_consistency_check_prompt(stage_id, stage_label, parsed_content,
                                   key_facts_registry) -> str:
    """Layer 1 校验：当前阶段 vs 全局关键事实清单"""
    from .key_facts import format_key_facts_for_prompt

    content_str = stringify_parsed(parsed_content)
    facts_str = format_key_facts_for_prompt(key_facts_registry)

    prompt = f"""你是资深小说策划审稿人。请检查当前阶段的生成内容是否与前序设定的关键事实一致。

##前序设定关键事实清单
{facts_str}

##当前阶段：{stage_label}
{content_str}

##校验维度
1. 实体一致性：人名、地名、势力名、物品名、术语是否与前序清单一致
2. 规则一致性：力量体系、世界观规则是否与前序冲突
3. 逻辑一致性：人物身份、势力关系、事件时序和人物年龄是否合理
4. 三角约束：三个及以上阶段共同定义的约束是否被同时满足

##输出格式
只输出 JSON，不要 markdown：
{{
  "_thought": "简要判断，100字以内",
  "overall_score": 0-100,
  "issues": [
    {{
      "severity": "high|medium|low",
      "aspect": "实体|规则|逻辑|三角约束",
      "conflicts_with": "premise|background|power_system|outline|characters|organizations|locations|items",
      "description": "问题描述，50-150字",
      "suggestion": "修正方向，50-150字"
    }}
  ],
  "highlights": ["一致的地方，50字以内"]
}}

##重要
<constraint>
- 只关注真实存在的矛盾，不要无病呻吟
- 若当前阶段与前序完全一致，issues 返回 []
- conflicts_with 字段必须明确指出与哪个前序阶段冲突</constraint>"""
    return prompt



def parse_consistency_check_response(text: str) -> dict:
    """解析一致性校验结果"""
    data = parse_stage_response(text)
    if not isinstance(data, dict):
        raise ValueError("校验结果不是 JSON 对象")

    score = data.get("overall_score", 100)
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 100
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
            "conflicts_with": (it.get("conflicts_with") or "").strip(),
            "description": (it.get("description") or "").strip(),
            "suggestion": (it.get("suggestion") or "").strip(),
        })

    return {
        "overall_score": score,
        "thought": (data.get("_thought") or "").strip(),
        "issues": issues,
        "highlights": [str(x).strip() for x in (data.get("highlights") or []) if str(x).strip()],
    }


def build_consistency_fix_prompt(stage_id, stage_label, parsed_content,
                                  issues, key_facts_registry) -> str:
    """基于一致性问题生成修正 patch（只修当前阶段）"""
    from .key_facts import format_key_facts_for_prompt

    content_str = stringify_parsed(parsed_content)
    facts_str = format_key_facts_for_prompt(key_facts_registry)

    issues_text = []
    for i, it in enumerate(issues):
        issues_text.append(
            f"{i + 1}. [{it['severity']}] {it['aspect']}"
            f"（与{it.get('conflicts_with', '?')}冲突）\n"
            f"   问题：{it['description']}\n   建议：{it['suggestion']}"
        )

    is_text_stage = stage_id in ("premise", "background", "power_system", "outline")

    if is_text_stage:
        field_map = {
            "premise": "premise",
            "background": "story_background",
            "power_system": "power_system",
            "outline": "outline",
        }
        field_hint = f"""##输出格式
{{
  "_thought": "说明",
  "patches": [
    {{"field": "{field_map[stage_id]}", "new_value": "修订后的完整文本"}}
  ]
}}"""
    else:
        field_hint = """##输出格式
{{
  "_thought": "说明",
  "patches": [
    {{"target_index": 0, "field": "字段名", "new_value": "新值"}}
  ]
}}
- target_index 为列表元素的索引（从 0 开始）
- 若需新增元素，target_index = -1，new_value 为完整对象
- 若需删除元素，target_index = 具体索引，new_value = null"""

    prompt = f"""你是小说策划。请根据一致性校验意见，修正当前阶段的内容。

##前序设定关键事实清单
{facts_str}

##当前阶段：{stage_label}
{content_str}

##需要修正的问题
{chr(10).join(issues_text)}

##修正原则
1. 只修正当前阶段，不要修改前序设定，【重点关注时间线和角色年龄设定的一致性】
2. 修正后必须与前序关键事实完全一致
3. 保持当前阶段的其他内容不变
4. 只输出需要改变的字段

{field_hint}"""
    return prompt

# ============================================================
# 故事弧拆解 + 批次章节生成
# ============================================================

def build_arc_planning_prompt(project, vol_idx: int, enable_golden_three: bool = False) -> str:
    """拆解某一卷为 3-6 个故事弧"""
    vol = project.volumes[vol_idx]
    parts = []
    if project.premise:
        parts.append(f"##核心矛盾\n{project.premise}")
    if project.story_background:
        parts.append(f"##故事背景\n{project.story_background}")
    if project.power_system:
        parts.append(f"##力量体系\n{project.power_system}")
    if project.outline:
        parts.append(f"##故事总纲\n{project.outline}")
    parts.append(f"##当前分卷\n{vol.title}\n卷摘要：{vol.summary or '（未提供）'}")

    if project.characters:
        lines = []
        for c in project.characters[:10]:
            line = f"- {c.name}"
            if c.personality:
                line += f"（{c.personality}）"
            lines.append(line)
        parts.append("##主要角色\n" + "\n".join(lines))

    context = "\n\n".join(parts)

    prompt = f"""你是小说策划。请把下面这一卷拆解为 3-6 个「故事弧」。

{context}

#任务
每个故事弧是一个独立的情节单元，包含：
- name：弧名（简洁有辨识度）
- goal：弧的核心目标（本弧要推进什么，300-800 字）
- estimated_chapters：预估章数（10-15章）
- key_turning_points：弧内 1-2 个关键转折点
- foreshadowing_to_plant：本弧需埋下的伏笔（0-3 条）
- foreshadowing_to_payoff：本弧需回收的伏笔（0-3 条，引用前弧埋下的）

##硬性要求
<contain>
1. 弧之间必须有清晰而连续的递进关系，故事情节不能明显断裂、重复，
- 【若拆解首卷弧，应在首弧规划快速展开完整的时代背景、货币、组织、力量体系等硬核设定，帮助读者快速理解整个世界，营造宏大或压迫的氛围】
</contain>
2. 每个弧的转折点必须与卷摘要一致，不得编造
3. 节奏上形成"起-承-转-合"的整体结构
4. 总章数应与卷摘要的体量匹配，适当引入日常描写丰富人物形象和时代背景
5. 伏笔尽量跨弧布置：前弧埋，后弧收
6. 弧数控制在 4-6 个

##输出格式
只输出 JSON，不要 markdown 标记或额外说明：
{{
  "_thought": "本卷的节奏如何安排、每弧的作用",
  "arcs": [
    {{
      "name": "弧名",
      "goal": "弧目标",
      "estimated_chapters": 10,
      "key_turning_points": ["转折1", "转折2"],
      "foreshadowing_to_plant": ["伏笔1"],
      "foreshadowing_to_payoff": []
    }}
  ]
}}"""
    # 原有 prompt 构造代码保持不变，在 return 前注入
    if enable_golden_three and vol_idx == 0:
        prompt += "\n" + build_golden_three_hint("arc")

    return prompt


def parse_arc_response(text: str) -> list:
    data = parse_stage_response(text)
    arcs = data.get("arcs", []) if isinstance(data, dict) else []
    result = []
    for a in arcs:
        if not isinstance(a, dict):
            continue
        name = (a.get("name") or "").strip()
        if not name:
            continue
        result.append({
            "name": name,
            "goal": (a.get("goal") or "").strip(),
            "estimated_chapters": int(a.get("estimated_chapters", 10) or 10),
            "key_turning_points": [
                str(x).strip() for x in (a.get("key_turning_points") or []) if str(x).strip()
            ],
            "foreshadowing_to_plant": [
                str(x).strip() for x in (a.get("foreshadowing_to_plant") or []) if str(x).strip()
            ],
            "foreshadowing_to_payoff": [
                str(x).strip() for x in (a.get("foreshadowing_to_payoff") or []) if str(x).strip()
            ],
        })
    return result


def _get_arc_chapters(vol, arc_idx: int):
    """取某弧下已生成的章节（保持原顺序）"""
    return [ch for ch in vol.chapters if ch.arc_idx == arc_idx]


def _build_rolling_summary(project, vol_idx: int, arc_idx: int,
                           before_count: int = None) -> str:
    """
    构建滚动摘要：只取弧内前 before_count 章的摘要。
    - before_count=None：取全部（用于弧内第一批之前的语境）
    - before_count=N：只取弧内前 N 章（用于生成/审核第 N+1 章起）
    """
    vol = project.volumes[vol_idx]
    arc = vol.arcs[arc_idx] if arc_idx < len(vol.arcs) else None
    arc_chapters_all = _get_arc_chapters(vol, arc_idx)

    # 按批次隔离：只保留前 before_count 章
    if before_count is not None:
        arc_chapters = arc_chapters_all[:max(0, before_count)]
    else:
        arc_chapters = arc_chapters_all

    lines = []
    if arc_chapters:
        lines.append("###本弧已生成章节")
        for i, ch in enumerate(arc_chapters, 1):
            if ch.plan:
                goal = ch.plan.goal or ch.plan.title or ""
                lines.append(f"  第{i}章 {ch.title}：{goal}")
            else:
                lines.append(f"  第{i}章 {ch.title}")
        lines.append("")

    # 最近 3 章完整规划
    if arc_chapters:
        recent = arc_chapters[-3:]
        lines.append("###最近章节完整规划")
        for ch in recent:
            if ch.plan:
                lines.append(f"  {ch.title}：")
                lines.append("    " + ch.plan.to_prompt_text().replace("\n", "\n    ")[:500])
        lines.append("")

    # 未回收伏笔：只统计到 before_count 之前
    active_fs = _get_active_foreshadowing(
        project, vol_idx, arc_idx, before_count=before_count
    )
    if active_fs:
        lines.append("###未回收伏笔")
        for fs in active_fs:
            lines.append(f"  - {fs}")
        lines.append("")

    # 已出场人物：只统计到 before_count 之前
    used = []
    for ch in arc_chapters:
        if ch.plan:
            for c in ch.plan.characters:
                if c not in used:
                    used.append(c)
    if used:
        lines.append(f"###本弧已出场人物\n{'、'.join(used)}")

    return "\n".join(lines).rstrip() if lines else "（本批为本弧的第一批章节，无前序摘要）"


def _get_active_foreshadowing(project, vol_idx: int, arc_idx: int,
                              before_count: int = None) -> list:
    """
    截止当前弧开始时仍未回收的伏笔。
    before_count：只统计弧内前 before_count 章内埋下且未回收的伏笔。
    """
    vol = project.volumes[vol_idx]
    active = []
    for i in range(arc_idx + 1):
        if i >= len(vol.arcs):
            break
        a = vol.arcs[i]
        for fs in a.foreshadowing_to_plant:
            if fs and fs not in active:
                active.append(fs)
        for fs in a.foreshadowing_to_payoff:
            if fs in active:
                active.remove(fs)

    # 章节内实际埋下但尚未回收的：只统计到 before_count 之前
    arc_chapters_all = _get_arc_chapters(vol, arc_idx)
    if before_count is not None:
        scan_chapters = arc_chapters_all[:max(0, before_count)]
    else:
        scan_chapters = arc_chapters_all

    for ch in scan_chapters:
        if not ch.plan:
            continue
        for fs in ch.plan.foreshadowing:
            if fs and fs not in active:
                active.append(fs)

    return active


def _build_hard_constraints(project, vol_idx: int, arc_idx: int) -> str:
    vol = project.volumes[vol_idx]
    arc = vol.arcs[arc_idx] if arc_idx < len(vol.arcs) else None

    items = []
    if project.premise:
        items.append(f"主线：{project.premise[:120]}")
    if arc:
        items.append(f"本弧目标：{arc.goal[:300]}")
        if arc.foreshadowing_to_payoff:
            items.append(f"本弧必须回收伏笔：{'、'.join(arc.foreshadowing_to_payoff)}")
        if arc.foreshadowing_to_plant:
            items.append(f"本弧必须埋伏笔：{'、'.join(arc.foreshadowing_to_plant)}")
    items.append("节奏：每 3-4 章一个高潮，避免连续铺垫")
    items.append("人物：本批新引入角色不超过 2 人")
    items.append("不得提前完成后续弧的情节")

    body = "\n".join(f"- {x}" for x in items)
    return f"【硬性约束】（不可违背，每批生成都必须遵守）\n{body}"


def build_arc_chapters_prompt(project, vol_idx: int, arc_idx: int,
                               batch_start: int, batch_size: int = 8,
                              enable_golden_three: bool = False,
                              existing_chapters=None,
                              user_guidance: str = "") -> str:
    """
    为某一弧生成一批章节。
    batch_start：本弧内从第几章开始（0-based）
    batch_size：本批生成多少章
    新增参数：
    - existing_chapters: list[Chapter]，用于 optimize 模式提供参考
    - user_guidance: str，用户调整指引
    """
    vol = project.volumes[vol_idx]
    if arc_idx >= len(vol.arcs):
        raise ValueError(f"弧索引 {arc_idx} 超出范围")
    arc = vol.arcs[arc_idx]

    total_arc_chapters = arc.estimated_chapters
    batch_end = min(batch_start + batch_size, total_arc_chapters)
    this_batch = batch_end - batch_start
    remaining_after = total_arc_chapters - batch_end

    constraints = _build_hard_constraints(project, vol_idx, arc_idx)
    # 关键修复：滚动摘要只包含"本批之前"的章节
    rolling = _build_rolling_summary(
        project, vol_idx, arc_idx, before_count=batch_start
    )

    # 前后弧提示（帮助 LLM 理解弧在整体中的位置）
    prev_arc_hint = ""
    if arc_idx > 0:
        prev = vol.arcs[arc_idx - 1]
        prev_arc_hint = f"前序弧：{prev.name}（{prev.goal}）"
    next_arc_hint = ""
    if arc_idx + 1 < len(vol.arcs):
        nxt = vol.arcs[arc_idx + 1]
        next_arc_hint = f"后续弧：{nxt.name}（{nxt.goal}）"

    # ---- 新增：参考章节 + 用户指引 ----
    extra_parts = []

    if existing_chapters:
        extra_parts.append("")
        extra_parts.append(
            "##已有章节规划（供参考，本次将重新生成整弧章节）"
        )
        for i, ch in enumerate(existing_chapters):
            plan = getattr(ch, "plan", None)
            extra_parts.append(f"第{i + 1}章 {ch.title}")
            if plan:
                if plan.goal:
                    extra_parts.append(f"  目标：{plan.goal}")
                if plan.key_events:
                    extra_parts.append(
                        f"  事件：{'；'.join(plan.key_events)}"
                    )
        extra_parts.append("")
        extra_parts.append(
            "参考上述已有章节的整体结构，但不要照搬。"
            "结合下方用户指引重新生成整弧的完整章节列表。"
        )

    if user_guidance:
        extra_parts.append("")
        extra_parts.append("##用户调整指引")
        extra_parts.append(user_guidance.strip())
        extra_parts.append("")
        extra_parts.append("请在重新生成时严格遵循上述指引：")
        extra_parts.append("1. 保留已有章节中合理的结构与情节")
        extra_parts.append("2. 严格按指引调整节奏、内容、重点")
        extra_parts.append("3. 生成全新的完整章节列表，不是局部修订")

    prompt = f"""{constraints}

##卷信息
第{vol_idx + 1}卷《{vol.title}》
卷摘要：{vol.summary}

##当前弧
{arc.to_prompt_text()}
{prev_arc_hint}
{next_arc_hint}

##滚动摘要
{rolling}

##本批任务
为当前弧生成第 {batch_start + 1} 到 {batch_end} 章，共 {this_batch} 章。
本弧共 {total_arc_chapters} 章，本批之后还剩 {remaining_after} 章。

{extra_parts}

##节奏要求
1. 第 {batch_start + 1} 章作为本批开篇，需尽快建立场景或承接上文冲突
2. 若本批包含弧内高潮章节（60-75% 位置），必须充分展开
3. 本批结尾（第 {batch_end} 章）应留下跨批悬念，引导读者继续
4. 每章结尾钩子要有差异，避免重复的悬念类型
5. 小说规划张弛有度，遵循3章一小高潮，5章一大高潮的设定基准，必须要有合理的冲突来调动读者的追读兴趣
 <contain>
6. 信息释放:【当章节作为小说开篇，规划需重点考虑设定信息如何在3-5章之内快速揭示，帮助读者迅速建立起对世界和时代背景、货币体系、组织、力量体系等设定的清晰认知】
</contain>

##人物与伏笔
1. 出场人物必须来自【主要角色】或本弧新引入角色（总数 ≤ 8）
2. 本批只埋伏笔清单中列出的伏笔
3. 已埋伏笔不在本批回收的，需在后续章节规划中保留（不要遗漏）

##内容纪律
1. 必须严格遵守背景设定的信息
2. 不得重复【滚动摘要】中已出现过的情节
3. 每章目标要具体，避免空泛（如"主角成长"太泛，应为"主角初次面对师门任务失败"）
4. 每章关键事件 2-3 条，每条要有推进感，适当引入日常描写和环境描写（简单说明烘托何种氛围），避免过度碎片化和俚语式的描述
5. 只输出本批次请求的章节 

##输出格式
只输出 JSON，不要 markdown 标记或额外说明：
{{
  "_thought": "本批如何承接上文、如何留悬念给下一批，200字左右",
  "chapters": [
    {{
      "title": "章节标题",
      "goal": "本章目标",
      "characters": ["角色名1", "角色名2"...间接出场的角色也是信息节点，必须纳入],
      "key_events": ["事件1", "事件2"...],
      "foreshadowing": ["伏笔1"],
      "ending_hook": "结尾钩子，100字以内，【避免过度碎片化】",
      "estimated_words": 2500-3000
    }}
  ]
}}"""

    # 原有的 golden three 注入保留
    if enable_golden_three and vol_idx == 0 and arc_idx == 0 \
            and batch_start <= 2:
        prompt += "\n" + build_golden_three_hint("chapters")

    return prompt

    return prompt


# def parse_chapter_plan_response(text: str) -> list:
#     """复用旧解析：兼容只有 chapters 的 JSON"""
#     data = parse_stage_response(text)
#     chapters = data.get("chapters", []) if isinstance(data, dict) else []
#     result = []
#     for c in chapters:
#         if not isinstance(c, dict):
#             continue
#         title = (c.get("title") or "").strip()
#         if not title:
#             continue
#         result.append({
#             "title": title,
#             "goal": (c.get("goal") or "").strip(),
#             "characters": [str(x).strip() for x in (c.get("characters") or []) if str(x).strip()],
#             "key_events": [str(x).strip() for x in (c.get("key_events") or []) if str(x).strip()],
#             "foreshadowing": [str(x).strip() for x in (c.get("foreshadowing") or []) if str(x).strip()],
#             "ending_hook": (c.get("ending_hook") or "").strip(),
#             "estimated_words": int(c.get("estimated_words", 3000) or 3000),
#         })
#     return result

