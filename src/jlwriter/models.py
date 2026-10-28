"""
章节分卷相关定义，包含历史记录、角色画像、关系、设定集、章节规划、故事弧
"""
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ChapterPlan:
    title: str = ""
    goal: str = ""
    characters: List[str] = field(default_factory=list)
    key_events: List[str] = field(default_factory=list)
    foreshadowing: List[str] = field(default_factory=list)
    ending_hook: str = ""
    estimated_words: int = 3000

    # ReAct 写作：细纲与实体清单
    detailed_outline: List[str] = field(default_factory=list)
    required_entities: dict = field(default_factory=dict)
    transition_notes: str = ""
    outline_thought: str = ""
    chapter_preference: str = ""   # 章节偏好：日常/战斗/抒情/紧张/悬疑/恐怖等，空为自由发挥

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "goal": self.goal,
            "characters": list(self.characters),
            "key_events": list(self.key_events),
            "foreshadowing": list(self.foreshadowing),
            "ending_hook": self.ending_hook,
            "estimated_words": self.estimated_words,
            "detailed_outline": list(self.detailed_outline),
            "required_entities": dict(self.required_entities),
            "transition_notes": self.transition_notes,
            "chapter_preference": self.chapter_preference,
            "outline_thought": self.outline_thought,
        }

    @staticmethod
    def from_dict(data: dict) -> 'ChapterPlan':
        return ChapterPlan(
            title=data.get("title", ""),
            goal=data.get("goal", ""),
            characters=list(data.get("characters", [])),
            key_events=list(data.get("key_events", [])),
            foreshadowing=list(data.get("foreshadowing", [])),
            ending_hook=data.get("ending_hook", ""),
            estimated_words=int(data.get("estimated_words", 3000) or 3000),
            detailed_outline=list(data.get("detailed_outline", [])),
            required_entities=dict(data.get("required_entities", {})),
            transition_notes=data.get("transition_notes", "") or "",
            chapter_preference=data.get("chapter_preference", "") or "",
            outline_thought=data.get("outline_thought", "") or "",
        )

    def to_prompt_text(self) -> str:
        lines = []
        if self.title:
            lines.append(f"章节名：{self.title}")
        if self.goal:
            lines.append(f"本章目标：{self.goal}")
        if self.characters:
            lines.append(f"出场人物：{'、'.join(self.characters)}")
        if self.key_events:
            lines.append("关键事件：")
            for e in self.key_events:
                lines.append(f"  - {e}")
        if self.foreshadowing:
            lines.append("需埋下的伏笔：")
            for f in self.foreshadowing:
                lines.append(f"  - {f}")
        if self.ending_hook:
            lines.append(f"结尾钩子：{self.ending_hook}")
        if self.chapter_preference:
            lines.append(f"章节偏好：{self.chapter_preference}")
        if self.detailed_outline:
            lines.append("细纲：")
            for i, step in enumerate(self.detailed_outline, 1):
                lines.append(f"  {i}. {step}")
        return "\n".join(lines)

    def has_detailed_outline(self) -> bool:
        return bool(self.detailed_outline)


@dataclass
class StoryArc:
    """故事弧：卷内的一个情节单元"""
    name: str = ""
    goal: str = ""
    estimated_chapters: int = 10
    key_turning_points: List[str] = field(default_factory=list)
    foreshadowing_to_plant: List[str] = field(default_factory=list)
    foreshadowing_to_payoff: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "goal": self.goal,
            "estimated_chapters": self.estimated_chapters,
            "key_turning_points": list(self.key_turning_points),
            "foreshadowing_to_plant": list(self.foreshadowing_to_plant),
            "foreshadowing_to_payoff": list(self.foreshadowing_to_payoff),
        }

    @staticmethod
    def from_dict(data: dict) -> 'StoryArc':
        return StoryArc(
            name=data.get("name", ""),
            goal=data.get("goal", ""),
            estimated_chapters=int(data.get("estimated_chapters", 10) or 10),
            key_turning_points=list(data.get("key_turning_points", [])),
            foreshadowing_to_plant=list(data.get("foreshadowing_to_plant", [])),
            foreshadowing_to_payoff=list(data.get("foreshadowing_to_payoff", [])),
        )

    def to_prompt_text(self) -> str:
        lines = [f"弧名：{self.name}", f"弧目标：{self.goal}",
                 f"预估章数：{self.estimated_chapters}"]
        if self.key_turning_points:
            lines.append("关键转折点：")
            for t in self.key_turning_points:
                lines.append(f"  - {t}")
        if self.foreshadowing_to_plant:
            lines.append(f"需埋伏笔：{'、'.join(self.foreshadowing_to_plant)}")
        if self.foreshadowing_to_payoff:
            lines.append(f"需回收伏笔：{'、'.join(self.foreshadowing_to_payoff)}")
        return "\n".join(lines)


# ============================================================
# 实体端点工具：统一使用 "type:name" 格式
# ============================================================

ENTITY_TYPES = {"character", "location", "organization", "item", "monster"}

ENTITY_TYPE_LABELS = {
    "character": "角色",
    "location": "地点",
    "organization": "组织",
    "item": "物品",
    "monster": "怪物",
}

ENTITY_TYPE_COLORS = {
    "character": "#4A90E2",
    "location": "#27AE60",
    "organization": "#8E44AD",
    "item": "#E67E22",
    "monster": "#C0392B",
}


def normalize_endpoint(raw) -> str:
    """确保端点带有类型前缀；无前缀时按 character: 处理"""
    if not raw:
        return ""
    raw = str(raw).strip()
    if ":" in raw:
        prefix = raw.split(":", 1)[0]
        if prefix in ENTITY_TYPES:
            return raw
    return f"character:{raw}"


def parse_endpoint(raw):
    """解析端点为 (type, name)"""
    if not raw:
        return ("", "")
    raw = str(raw).strip()
    if ":" in raw:
        prefix, name = raw.split(":", 1)
        if prefix in ENTITY_TYPES:
            return (prefix, name)
    return ("character", raw)


def format_endpoint(entity_type: str, name: str) -> str:
    if not name:
        return ""
    return f"{entity_type}:{name}"


def display_endpoint(raw) -> str:
    """用于 UI 展示：只显示名称部分"""
    _, name = parse_endpoint(raw)
    return name


@dataclass
class Chapter:
    title: str = "新章节"
    content: str = ""
    summary: str = ""
    plan: Optional[ChapterPlan] = None
    arc_idx: int = -1      # 所属弧索引，-1 表示未归属


@dataclass
class Volume:
    title: str = "新分卷"
    summary: str = ""
    arcs: List[StoryArc] = field(default_factory=list)
    chapters: List[Chapter] = field(default_factory=list)


@dataclass
class CharacterProfile:
    """角色画像：外貌、性格、习惯、时间线、别名、当前状态"""
    name: str = ""
    appearance: str = ""
    personality: str = ""
    habits: str = ""
    timeline: List[str] = field(default_factory=list)
    aliases: List[str] = field(default_factory=list)

    # 当前状态（随章节更新，最新值覆盖旧值）
    age: str = ""
    power_level: str = ""
    emotion: str = ""
    health: str = ""
    status_notes: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "appearance": self.appearance,
            "personality": self.personality,
            "habits": self.habits,
            "timeline": list(self.timeline),
            "aliases": list(self.aliases),
            "age": self.age,
            "power_level": self.power_level,
            "emotion": self.emotion,
            "health": self.health,
            "status_notes": self.status_notes,
        }

    @staticmethod
    def from_dict(data: dict) -> 'CharacterProfile':
        return CharacterProfile(
            name=data.get("name", ""),
            appearance=data.get("appearance", ""),
            personality=data.get("personality", ""),
            habits=data.get("habits", ""),
            timeline=list(data.get("timeline", [])),
            aliases=list(data.get("aliases", [])),
            age=data.get("age", "") or "",
            power_level=data.get("power_level", "") or "",
            emotion=data.get("emotion", "") or "",
            health=data.get("health", "") or "",
            status_notes=data.get("status_notes", "") or "",
        )

    def is_dead(self) -> bool:
        keywords = ("死亡", "身亡", "牺牲", "殒命", "遇害", "阵亡", "殁")
        if self.health and any(k in self.health for k in keywords):
            return True
        return any(any(k in ev for k in keywords) for ev in self.timeline)

    def format_status_for_prompt(self) -> str:
        """把状态字段拼成 prompt 用的一行文本"""
        parts = []
        if self.age:
            parts.append(f"年龄={self.age}")
        if self.power_level:
            parts.append(f"力量等级={self.power_level}")
        if self.emotion:
            parts.append(f"情绪={self.emotion}")
        if self.health:
            parts.append(f"健康={self.health}")
        if self.status_notes:
            parts.append(f"其他={self.status_notes}")
        return "；".join(parts)

    def has_status(self) -> bool:
        return bool(self.age or self.power_level or self.emotion
                    or self.health or self.status_notes)


@dataclass
class Location:
    name: str = ""
    level: str = ""
    parent: str = ""
    description: str = ""

    def to_dict(self):
        return {"name": self.name, "level": self.level,
                "parent": self.parent, "description": self.description}

    @staticmethod
    def from_dict(data):
        return Location(
            name=data.get("name", ""), level=data.get("level", ""),
            parent=data.get("parent", ""), description=data.get("description", ""),
        )


@dataclass
class Organization:
    name: str = ""
    nature: str = ""
    description: str = ""
    members: List[str] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "nature": self.nature,
                "description": self.description, "members": list(self.members),
                "relations": [dict(r) for r in self.relations]}

    @staticmethod
    def from_dict(data):
        return Organization(
            name=data.get("name", ""), nature=data.get("nature", ""),
            description=data.get("description", ""),
            members=list(data.get("members", [])),
            relations=[dict(r) for r in data.get("relations", []) if isinstance(r, dict)],
        )


@dataclass
class Item:
    name: str = ""
    type: str = ""
    description: str = ""
    ability: str = ""
    owner: str = ""

    def to_dict(self):
        return {"name": self.name, "type": self.type,
                "description": self.description, "ability": self.ability,
                "owner": self.owner}

    @staticmethod
    def from_dict(data):
        return Item(
            name=data.get("name", ""), type=data.get("type", ""),
            description=data.get("description", ""), ability=data.get("ability", ""),
            owner=data.get("owner", ""),
        )

@dataclass
class Monster:
    name: str = ""
    aliases: List[str] = field(default_factory=list)
    appearance: str = ""            # 外形
    behavior_ability: str = ""      # 行为与能力
    category: str = ""              # 纲目（可选），如"妖兽-蛇形-黑鳞蛟科"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "aliases": list(self.aliases),
            "appearance": self.appearance,
            "behavior_ability": self.behavior_ability,
            "category": self.category,
        }

    @staticmethod
    def from_dict(data: dict) -> 'Monster':
        return Monster(
            name=data.get("name", ""),
            aliases=list(data.get("aliases", [])),
            appearance=data.get("appearance", ""),
            behavior_ability=data.get("behavior_ability", ""),
            category=data.get("category", ""),
        )

@dataclass
class CharacterState:
    """角色在某一章末尾的即时状态"""
    name: str = ""
    location: str = ""              # 当前位置
    physical: str = ""              # 健康/受伤/中毒/昏迷/死亡
    power_level: str = ""           # 修为或能力等级
    emotion: str = ""               # 显著的情感状态
    known_secrets: List[str] = field(default_factory=list)   # 已知的重要秘密
    current_goal: str = ""          # 当前目标/意图

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "location": self.location,
            "physical": self.physical,
            "power_level": self.power_level,
            "emotion": self.emotion,
            "known_secrets": list(self.known_secrets),
            "current_goal": self.current_goal,
        }

    @staticmethod
    def from_dict(data: dict) -> 'CharacterState':
        return CharacterState(
            name=data.get("name", ""),
            location=data.get("location", ""),
            physical=data.get("physical", ""),
            power_level=data.get("power_level", ""),
            emotion=data.get("emotion", ""),
            known_secrets=list(data.get("known_secrets", [])),
            current_goal=data.get("current_goal", ""),
        )


@dataclass
class WorldState:
    """截至某一章末尾的世界状态快照"""
    up_to_volume: int = -1          # 卷索引（0-based）
    up_to_chapter: int = -1         # 章索引（0-based）
    story_time: str = ""            # 故事内时间
    current_location: str = ""      # 主视角所在位置
    character_states: List[CharacterState] = field(default_factory=list)
    organization_states: List[dict] = field(default_factory=list)
    item_locations: List[dict] = field(default_factory=list)
    active_threads: List[str] = field(default_factory=list)  # 未收束的情节线

    def to_dict(self) -> dict:
        return {
            "up_to_volume": self.up_to_volume,
            "up_to_chapter": self.up_to_chapter,
            "story_time": self.story_time,
            "current_location": self.current_location,
            "character_states": [c.to_dict() for c in self.character_states],
            "organization_states": [dict(o) for o in self.organization_states],
            "item_locations": [dict(i) for i in self.item_locations],
            "active_threads": list(self.active_threads),
        }

    @staticmethod
    def from_dict(data: dict) -> 'WorldState':
        ws = WorldState(
            up_to_volume=int(data.get("up_to_volume", -1) or -1),
            up_to_chapter=int(data.get("up_to_chapter", -1) or -1),
            story_time=data.get("story_time", "") or "",
            current_location=data.get("current_location", "") or "",
            active_threads=list(data.get("active_threads", [])),
        )
        for c in data.get("character_states", []) or []:
            if isinstance(c, dict):
                ws.character_states.append(CharacterState.from_dict(c))
        for o in data.get("organization_states", []) or []:
            if isinstance(o, dict):
                ws.organization_states.append(dict(o))
        for i in data.get("item_locations", []) or []:
            if isinstance(i, dict):
                ws.item_locations.append(dict(i))
        return ws


@dataclass
class HistoryEntry:
    timestamp: str
    data: dict
    chapter_count: int = 0
    total_word_count: int = 0
    current_volume_title: str = ""
    current_chapter_title: str = ""
    current_volume_index: int = -1
    current_chapter_index: int = -1


@dataclass
class StoryProject:
    title: str = "未命名故事"
    settings_book: str = ""
    story_background: str = ""
    premise: str = ""
    power_system: str = ""
    outline: str = ""
    volumes: List[Volume] = field(default_factory=list)
    history: List[HistoryEntry] = field(default_factory=list)
    characters: List[CharacterProfile] = field(default_factory=list)
    relations: List[dict] = field(default_factory=list)
    locations: List[Location] = field(default_factory=list)
    organizations: List[Organization] = field(default_factory=list)
    items: List[Item] = field(default_factory=list)
    world_states: List[WorldState] = field(default_factory=list)  # 新增
    monsters: List[Monster] = field(default_factory=list)   #怪物

    def to_dict(self) -> dict:
        return {
            "title": self.title,
            "settings_book": self.settings_book,
            "story_background": self.story_background,
            "premise": self.premise,
            "power_system": self.power_system,
            "outline": self.outline,
            "world_states": [ws.to_dict() for ws in self.world_states],  # 新增
            "volumes": [
                {
                    "title": v.title,
                    "summary": v.summary,
                    "arcs": [a.to_dict() for a in v.arcs],
                    "chapters": [
                        {
                            "title": c.title,
                            "content": c.content,
                            "summary": c.summary,
                            "plan": c.plan.to_dict() if c.plan else None,
                            "arc_idx": c.arc_idx,
                        }
                        for c in v.chapters
                    ]
                }
                for v in self.volumes
            ],
            "characters": [c.to_dict() for c in self.characters],
            "relations": [dict(r) for r in self.relations],
            "locations": [l.to_dict() for l in self.locations],
            "organizations": [o.to_dict() for o in self.organizations],
            "items": [i.to_dict() for i in self.items],
            "monsters": [m.to_dict() for m in self.monsters],
        }

    @staticmethod
    def from_dict(data: dict) -> 'StoryProject':
        proj = StoryProject(title=data.get("title", "未命名故事"))
        proj.settings_book = data.get("settings_book", "") or ""
        proj.story_background = data.get("story_background", "") or ""
        proj.premise = data.get("premise", "") or ""
        proj.power_system = data.get("power_system", "") or ""
        proj.outline = data.get("outline", "") or ""
        for ws_data in data.get("world_states", []) or []:
            if isinstance(ws_data, dict):
                proj.world_states.append(WorldState.from_dict(ws_data))
        for v_data in data.get("volumes", []):
            vol = Volume(title=v_data.get("title", "新分卷"),
                         summary=v_data.get("summary", ""))
            for a_data in v_data.get("arcs", []):
                vol.arcs.append(StoryArc.from_dict(a_data))

            for c_data in v_data.get("chapters", []):
                # 修复：显式判断，避免 0 被 falsy 判断吞掉
                raw_arc = c_data.get("arc_idx", -1)
                if raw_arc is None:
                    arc_idx = -1
                else:
                    try:
                        arc_idx = int(raw_arc)
                    except (TypeError, ValueError):
                        arc_idx = -1

                ch = Chapter(
                    title=c_data.get("title", "新章节"),
                    content=c_data.get("content", ""),
                    summary=c_data.get("summary", ""),
                    arc_idx=arc_idx,
                )
                plan_data = c_data.get("plan")
                if isinstance(plan_data, dict):
                    ch.plan = ChapterPlan.from_dict(plan_data)
                vol.chapters.append(ch)

            # 一致性校验：若 arc_idx 越界（例如弧被删过），降级为 -1
            valid_arc_range = range(len(vol.arcs))
            for ch in vol.chapters:
                if ch.arc_idx >= 0 and ch.arc_idx not in valid_arc_range:
                    # 弧索引失效，归到未分类，避免 UI 中出现"幽灵弧"
                    ch.arc_idx = -1

            proj.volumes.append(vol)

        for c_data in data.get("characters", []):
            proj.characters.append(CharacterProfile.from_dict(c_data))
        # 关系：将旧格式（无类型前缀）迁移为新格式
        for r_data in data.get("relations", []):
            if not isinstance(r_data, dict):
                continue
            migrated = dict(r_data)
            a = normalize_endpoint(migrated.get("from", ""))
            b = normalize_endpoint(migrated.get("to", ""))
            if not a or not b:
                continue
            migrated["from"] = a
            migrated["to"] = b
            proj.relations.append(migrated)
        for l_data in data.get("locations", []):
            proj.locations.append(Location.from_dict(l_data))
        for o_data in data.get("organizations", []):
            proj.organizations.append(Organization.from_dict(o_data))
        for i_data in data.get("items", []):
            proj.items.append(Item.from_dict(i_data))
        for m_data in data.get("monsters", []):
            if isinstance(m_data, dict):
                proj.monsters.append(Monster.from_dict(m_data))
        return proj

@dataclass
class DimensionDeviation:
    """单个维度的偏离情况"""
    dimension: str = ""      # goal / characters / key_events / foreshadowing / ending_hook
    status: str = ""         # achieved / partial / deviated / missing
    planned: str = ""        # 规划内容
    actual: str = ""         # 实际内容
    comment: str = ""        # 对比说明


@dataclass
class PlanDeviationReport:
    """章节规划偏离报告（临时分析结果，不持久化）"""
    chapter_title: str = ""
    overall_score: int = 0
    summary: str = ""
    suggestions: str = ""
    dimensions: List[DimensionDeviation] = field(default_factory=list)
    extra_content: List[str] = field(default_factory=list)

    @property
    def level(self) -> str:
        """根据分数返回等级"""
        s = self.overall_score
        if s >= 90:
            return "优秀"
        if s >= 75:
            return "良好"
        if s >= 60:
            return "基本符合"
        if s >= 40:
            return "部分偏离"
        return "明显偏离"

    @property
    def color(self) -> str:
        """分数对应的颜色"""
        s = self.overall_score
        if s >= 75:
            return "#4CAF50"
        if s >= 60:
            return "#FF9800"
        return "#F44336"