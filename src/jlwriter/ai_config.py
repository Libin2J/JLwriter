"""
写作助手设置保存
"""
import json
import base64
import os
from .agents import AGENT_DEFINITIONS, AgentConfig, ResolvedAgent

CONFIG_PATH = os.path.join(os.path.expanduser('~'), '.story_editor_ai_config.json')
SECRET_KEY = b"StoryEditor2024!AI"

# 预设写作风格
DEFAULT_STYLES = [
    "简洁流畅", "华丽优美", "幽默轻松", "严谨学术",
    "热血爽文", "悬疑紧张", "黑暗沉重",
    "童话", "克苏鲁",
]

# 模型服务商配置：base_url、模型列表、默认模型
MODEL_PROVIDERS = {
    "deepseek": {
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-flash", "deepseek-v4-pro"],
        "default_model": "deepseek-flash",
    },
    "openai": {
        "label": "OpenAI",
        "base_url": None,  # 使用默认 https://api.openai.com/v1
        "models": ["gpt-3.5-turbo", "gpt-4o", "gpt-4o-mini"],
        "default_model": "gpt-3.5-turbo",
    },
    "qwen": {
        "label": "Qwen（阿里云百炼）",
        # 使用国际站通用域名，避免 WorkspaceId 依赖
        "base_url": "https://ws-qozb8whn95ksm05n.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
        "models": [
            "qwen3.8-max",
            "qwen3.8-flash",
            "qwen3.8-2.4t-a95b",
            "qwen3.7-plus",
            "kimi/kimi-k3",
        ],
        "default_model": "qwen3.8-flash",
    },
    "gemini": {
        "label": "Gemini（Google）",
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "models": [
            "gemini-3.8-flash",
            "gemini-3.8-pro",
            "gemini-2.5-flash",
            "gemini-2.5-pro",
        ],
        "default_model": "gemini-3.8-flash",
    },
    "glm": {
        "label": "GLM（智谱AI）",
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "models": [
            "glm-5.3",
            "glm-5.3-flash",
            "glm-5.2",
        ],
        "default_model": "glm-5.3",
    },
    "claude": {
        "label": "Claude（Anthropic）",
        "base_url": "https://api.anthropic.com/v1/",
        "models": [
            "claude-opus-5-5",
            "claude-opus-5-0",
            "claude-sonnet-4-6",
        ],
        "default_model": "claude-sonnet-4-5",
    },
}

def _xor_encrypt(text: str) -> str:
    if not text:
        return ""
    data = text.encode('utf-8')
    key = SECRET_KEY * (len(data) // len(SECRET_KEY) + 1)
    encrypted = bytes([d ^ k for d, k in zip(data, key)])
    return base64.b64encode(encrypted).decode()


def _xor_decrypt(token: str) -> str:
    if not token:
        return ""
    encrypted = base64.b64decode(token)
    key = SECRET_KEY * (len(encrypted) // len(SECRET_KEY) + 1)
    data = bytes([e ^ k for e, k in zip(encrypted, key)])
    return data.decode('utf-8')


class AIConfig:
    def __init__(self):
        self.api_keys = {}       # provider → key
        self.style = "简洁流畅"
        self.custom_styles = []
        self.enable_continue = True
        self.enable_outline = True
        self.context_length = "500字"
        self.assistant_enabled = True
        self.include_l1_rules = True   # 是否在续写上下文中包含完整的 L1b 世界规则
        self.include_l1_outline = False   # L1 中是否包含故事总纲（续写单章时通常不需要）
        self.enable_l0_world_state = False  # 新增L0层级信息：默认关闭
        self.enable_golden_three_chapters = False  # 黄金三章设计开关

        # 各 agent 独立配置
        self.agents = {}
        for name, defn in AGENT_DEFINITIONS.items():
            self.agents[name] = AgentConfig(
                name=name,
                enabled=True,
                provider="deepseek",
                model="",
                persona=defn["default_persona"],
                use_style=defn.get("use_style", False),
            )

    # ---------- API Key ----------
    def get_api_key(self, provider: str) -> str:
        return self.api_keys.get(provider, "")

    def set_api_key(self, provider: str, key: str):
        self.api_keys[provider] = key or ""

    # ---------- Agent 解析 ----------
    def resolve_agent(self, name: str) -> ResolvedAgent:
        agent = self.agents.get(name)
        if not agent:
            return None
        provider = agent.provider or "deepseek"
        meta = MODEL_PROVIDERS.get(provider, MODEL_PROVIDERS["deepseek"])
        model = agent.model or meta["default_model"]
        persona = agent.persona or AGENT_DEFINITIONS[name]["default_persona"]
        style = self.style if agent.use_style else ""
        return ResolvedAgent(
            name=name,
            provider=provider,
            model=model,
            api_key=self.get_api_key(provider),
            base_url=meta.get("base_url"),
            persona=persona,
            style=style,
        )

    def is_agent_enabled(self, name: str) -> bool:
        agent = self.agents.get(name)
        return bool(agent and agent.enabled)

    # ---------- 持久化 ----------
    def save(self):
        encrypted_keys = {}
        for provider, key in self.api_keys.items():
            if key:
                encrypted_keys[provider] = _xor_encrypt(key)

        agents_data = {}
        for name, agent in self.agents.items():
            agents_data[name] = {
                "enabled": agent.enabled,
                "provider": agent.provider,
                "model": agent.model,
                "persona": agent.persona,
                "use_style": agent.use_style,
            }

        data = {
            "api_keys": encrypted_keys,
            "style": self.style,
            "custom_styles": list(self.custom_styles),
            "enable_continue": self.enable_continue,
            "enable_outline": self.enable_outline,
            "context_length": self.context_length,
            "assistant_enabled": self.assistant_enabled,
            "agents": agents_data,
            "include_l1_rules": self.include_l1_rules,
            "include_l1_outline": self.include_l1_outline,
            "enable_l0_world_state": self.enable_l0_world_state,  # 新增
            "enable_golden_three_chapters": self.enable_golden_three_chapters,
        }
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self):
        if not os.path.exists(CONFIG_PATH):
            return False
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # API Keys
            self.api_keys = {}
            raw_keys = data.get("api_keys")
            if isinstance(raw_keys, dict):
                for provider, token in raw_keys.items():
                    try:
                        self.api_keys[provider] = _xor_decrypt(token)
                    except Exception:
                        pass
            # 兼容极旧格式：单 api_key 字段
            if not self.api_keys and data.get("api_key"):
                old_type = data.get("api_type", "deepseek")
                try:
                    self.api_keys[old_type] = _xor_decrypt(data["api_key"])
                except Exception:
                    pass

            # 全局设置
            self.style = data.get("style", "简洁流畅")
            self.custom_styles = list(data.get("custom_styles", []))
            self.enable_continue = data.get("enable_continue", True)
            self.enable_outline = data.get("enable_outline", True)
            self.context_length = data.get("context_length", "500字")
            self.assistant_enabled = data.get("assistant_enabled", True)
            # load
            self.include_l1_rules = data.get("include_l1_rules", True)
            self.include_l1_outline = data.get("include_l1_outline", False)
            self.enable_l0_world_state = data.get("enable_l0_world_state", False)  # 新增
            self.enable_golden_three_chapters = data.get(
                "enable_golden_three_chapters", False
            )
            # Agents
            agents_data = data.get("agents")
            if isinstance(agents_data, dict) and agents_data:
                self._load_agents_new(agents_data)
            else:
                self._migrate_from_legacy(data)

            return True
        except Exception as e:
            print("加载 AI 配置失败:", e)
            return False

    def _load_agents_new(self, agents_data):
        for name, defn in AGENT_DEFINITIONS.items():
            ad = agents_data.get(name, {})
            self.agents[name] = AgentConfig(
                name=name,
                enabled=ad.get("enabled", True),
                provider=ad.get("provider", "deepseek"),
                model=ad.get("model", ""),
                persona=ad.get("persona", "") or defn["default_persona"],
                use_style=ad.get("use_style", defn.get("use_style", False)),
            )

    def _migrate_from_legacy(self, data):
        """从旧版单 agent 配置迁移到多 agent 配置"""
        old_type = data.get("api_type", "deepseek")
        old_model = data.get("model_name", "")
        old_persona = data.get("persona", "")
        old_enhance_provider = data.get("enhance_provider", "")
        old_enhance_model = data.get("enhance_model", "")
        old_enhance_persona = data.get("enhance_persona", "")

        for name, defn in AGENT_DEFINITIONS.items():
            self.agents[name].provider = old_type
            self.agents[name].model = ""
            self.agents[name].persona = defn["default_persona"]
            self.agents[name].use_style = defn.get("use_style", False)

        # writer 承接旧的 persona 与 model_name
        if old_persona:
            self.agents["writer"].persona = old_persona
        if old_model:
            self.agents["writer"].model = old_model

        # enhancer 承接旧的 enhance_* 配置（provider/model/persona 仍沿用）
        if old_enhance_provider:
            self.agents["enhancer"].provider = old_enhance_provider
        if old_enhance_model:
            self.agents["enhancer"].model = old_enhance_model
        if old_enhance_persona:
            self.agents["enhancer"].persona = old_enhance_persona