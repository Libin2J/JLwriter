"""
Agent 定义与运行时解析：多 agent 协作范式的基础
"""
from dataclasses import dataclass


AGENT_DEFINITIONS = {
    "writer": {
        "label": "写作 Agent",
        "description": "负责正文续写、章节扩写",
        "use_style": True,
        "user_hint": (
            "负责正文写作任务。开启后，AI 对话窗口中的「续写当前章节」"
            "会使用此 Agent 生成正文。\n"
            "建议选择长上下文、创作能力强的旗舰模型（如 DeepSeek、Claude Opus）。"
        ),
        "default_persona": (
            "你是一位专业的小说作家。你的任务是续写小说正文。\n"
            "要求：\n"
            "1. 保持与前文的连贯，人物性格、对话风格一致，前后逻辑严谨\n"
            "2. 严格遵守设定集和故事背景\n"
            "3. 续写时保持人物内心独白的严格独立性\n"
            "4. 严格避免重复描写和过度修辞\n"
            "5. 对话应口语化，不得过度简短\n"
            "6. 若大纲情节比正文超前，严格按大纲展开，不私自修改情节"
        ),
    },
    "enhancer": {
        "label": "编辑 Agent",
        "description": "对正文进行精修、去 AI 味、提升文笔",
        "user_hint": (
            "负责精修文本，有两个用途：\n"
            "① 启用「续写增强」时，自动对写作 Agent 的输出进行二次精修；\n"
            "② 用户手动点击「AI 精修本章」时使用。\n"
            "建议选择文笔好、响应快的模型（如 Claude Sonnet、GLM）。"
        ),
        "use_style": True,
        "default_persona": (
            "你是一位资深文字编辑。你的任务是精修给定文本。\n"
            "要求：\n"
            "1. 保留原意与情节细节，绝对不能改变故事走向\n"
            "2. 去除 AI 味：删除机械的排比、对称句、空洞的形容词\n"
            "3. 提升文笔：语言更自然、对话更口语、叙述更有节奏\n"
            "4. 保持人物语气和性格的一致性\n"
            "5. 只输出精修后的文本，不要解释"
        ),
    },
    "outliner": {
        "label": "大纲 Agent",
        "description": "生成章节结构化大纲",
        "user_hint": (
            "负责生成章节结构化大纲。点击「立即整理大纲」时使用。\n"
            "输出需为严格 JSON 格式，建议选择指令遵循能力强、"
            "JSON 输出稳定的模型，推荐配置为Qwen-flash系列的便宜模型。"
        ),
        "use_style": False,
        "default_persona": (
            "你是一位专业的小说编辑。你的任务是为章节生成结构化大纲。\n"
            "严格按照时间、地点、人物、故事线、结果五个字段输出。"
        ),
    },
    "extractor": {
        "label": "档案提取 Agent",
        "description": "从章节中提取角色画像、地点、物品、机构与关系档案",
        "user_hint": (
            "负责从章节正文中提取故事档案（角色 / 地点 / 物品 / 组织 / 关系）。\n"
            "提取故事档案、规划差异校验时使用。\n"
            "建议选择长上下文、结构化输出稳定的模型。"
        ),
        "use_style": False,
        "default_persona": (
            "你是专业的小说角色与关系提取助手，服务于长篇小说的"
            "人物档案库构建。"
        ),
    },
    "planner": {
        "label": "策划 Agent",
        "description": "根据预设从零构建完整世界观与故事框架",
        "user_hint": (
            "负责世界观构建与规划。AI 策划、拆解故事弧、生成章节规划、"
            "展开细纲时使用。\n"
            "任务最复杂、对推理能力要求最高，建议使用当前可用的最强模型"
        ),
        "use_style": False,
        "default_persona": (
            "你是一位资深的小说策划与世界观构建师。你的任务是根据"
            "用户预设，逐步构建完整、自洽、有深度的故事设定。\n"
            "要求：\n"
            "1. 严格遵循用户预设的题材、主题、基调\n"
            "2. 各阶段设定之间必须保持内在一致\n"
            "3. 输出内容要具体、有画面感，避免空泛\n"
            "4. 每个阶段先思考再输出，思考放在 _thought 字段\n"
            "5. 只输出合法的 JSON，不要 markdown 标记或额外解释"
        ),
    },
    "reviewer": {
        "label": "审核 Agent",
        "description": "对大纲、故事弧、章节规划进行二次审核与优化",
        "user_hint": (
            "负责审核与修正。校验一致性、审核章节规划、生成世界状态快照、"
            "修正正文时使用。\n"
            "高频调用，建议选择响应快、成本低的模型"
            "（如 Claude Haiku、GLM-Flash、DeepSeek-flash）。"
        ),
        "use_style": False,
        "default_persona": (
            "你是一位资深小说策划审稿人，擅长发现设定中的逻辑漏洞、"
            "节奏失衡、伏笔断裂与人物动机不足。你的审查客观、具体、可执行。\n"
            "要求：\n"
            "1. 只指出真实存在的问题，不无病呻吟\n"
            "2. 每条问题必须给出具体的修改建议\n"
            "3. 若某方面做得不错，也要指出\n"
            "4. 只输出合法 JSON，必须考虑输出长度限制"
        ),
    },
    ######
    # 如需扩展其他Agent，可按照上述格式在此处继续添加
    ######
}


@dataclass
class AgentConfig:
    name: str
    enabled: bool = True
    provider: str = "deepseek"
    model: str = ""
    persona: str = ""
    use_style: bool = False


@dataclass
class ResolvedAgent:
    """运行时解析后的 agent 配置，供 AIRequestThread 直接使用"""
    name: str
    provider: str
    model: str
    api_key: str
    base_url: str
    persona: str
    style: str      # 空字符串表示不注入风格