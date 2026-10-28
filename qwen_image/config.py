"""配置解析：API Key、接入点、模型名。

优先级（从高到低）：

1. 显式参数（``api_key=`` / ``--api-key`` 等）
2. 环境变量
3. JLwriter 桌面应用的配置（仅在 ``use_jlwriter=True`` 时读取）

所有环境变量名集中定义在下方，方便查阅与文档同步。
"""
from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence, Tuple

from .errors import QwenImageConfigError

# ---------------------------------------------------------------- 默认值
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com"
DEFAULT_MODEL = "qwen-image-3.0"
DEFAULT_PROTOCOL = "openai"

# ---------------------------------------------------------------- 环境变量
API_KEY_ENV_VARS: Tuple[str, ...] = (
    "QWEN_IMAGE_API_KEY",
    "DASHSCOPE_API_KEY",
    "QWEN_API_KEY",
)
BASE_URL_ENV_VARS: Tuple[str, ...] = (
    "QWEN_IMAGE_BASE_URL",
    "DASHSCOPE_BASE_URL",
)
MODEL_ENV_VARS: Tuple[str, ...] = ("QWEN_IMAGE_MODEL",)
WORKSPACE_ENV_VARS: Tuple[str, ...] = (
    "QWEN_IMAGE_WORKSPACE_ID",
    "DASHSCOPE_WORKSPACE_ID",
)

# ---------------------------------------------------------------- JLwriter 复用
# 与 ``src/jlwriter/ai_config.py`` 保持一致的路径与异或密钥。
JLWRITER_CONFIG_PATH = Path.home() / ".story_editor_ai_config.json"
JLWRITER_SECRET = b"StoryEditor2024!AI"


@dataclass
class Credentials:
    """一次解析结果，``source`` 用于排查“这个 Key 到底从哪来的”。"""

    api_key: Optional[str]
    base_url: str
    source: str


def first_env(names: Sequence[str]) -> Optional[str]:
    """返回第一个非空环境变量值。"""
    for name in names:
        value = os.environ.get(name)
        if value and value.strip():
            return value.strip()
    return None


def _xor_decrypt(token: str) -> str:
    """解密 JLwriter 写入的异或 + Base64 字符串。"""
    if not token:
        return ""
    raw = base64.b64decode(token)
    key = JLWRITER_SECRET * (len(raw) // len(JLWRITER_SECRET) + 1)
    data = bytes([byte ^ k for byte, k in zip(raw, key)])
    return data.decode("utf-8")


def _jlwriter_qwen_base_url() -> Optional[str]:
    """从已安装的 jlwriter 包中取出 Qwen 的接入点。

    该接入点与 Key 属于同一个业务空间，必须成对使用；
    读不到就返回 ``None``，由调用方回退到默认地址。
    """
    try:  # 该插件可以脱离 JLwriter 单独使用，导入失败属于正常情况
        from jlwriter.ai_config import MODEL_PROVIDERS  # type: ignore

        url = (MODEL_PROVIDERS.get("qwen") or {}).get("base_url")
        return url.strip() if isinstance(url, str) and url.strip() else None
    except Exception:
        return None


def load_jlwriter_credentials(
    path: Optional[Path] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """读取 JLwriter 保存的 Qwen API Key。

    返回 ``(api_key, base_url)``，任一缺失时为 ``None``。
    文件不存在或格式异常时静默返回空值，由上层决定是否报错。
    """
    config_path = Path(path) if path else JLWRITER_CONFIG_PATH
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return None, None

    token = (data.get("api_keys") or {}).get("qwen")
    if not isinstance(token, str) or not token:
        return None, None
    try:
        api_key = _xor_decrypt(token)
    except Exception:
        return None, None
    if not api_key:
        return None, None
    return api_key, _jlwriter_qwen_base_url()


def _expand_workspace(url: str, workspace_id: Optional[str]) -> str:
    """展开 ``https://{workspace_id}.cn-beijing.maas.aliyuncs.com`` 这类模板。"""
    url = url.strip()
    if "{workspace_id}" not in url:
        return url
    if not workspace_id:
        raise QwenImageConfigError(
            "base_url 中包含 {workspace_id} 占位符，请同时提供 workspace_id "
            "（--workspace-id 或环境变量 QWEN_IMAGE_WORKSPACE_ID）。"
        )
    return url.replace("{workspace_id}", workspace_id.strip())


def resolve_base_url(
    base_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
) -> str:
    """解析接入点，统一去掉结尾斜杠。"""
    url = (base_url or first_env(BASE_URL_ENV_VARS) or DEFAULT_BASE_URL).strip()
    url = _expand_workspace(url, workspace_id or first_env(WORKSPACE_ENV_VARS))
    if not url.startswith(("http://", "https://")):
        raise QwenImageConfigError(f"base_url 必须以 http:// 或 https:// 开头：{url!r}")
    return url.rstrip("/")


def resolve_credentials(
    api_key: Optional[str] = None,
    base_url: Optional[str] = None,
    workspace_id: Optional[str] = None,
    use_jlwriter: bool = False,
) -> Credentials:
    """按优先级解析出 ``(api_key, base_url)``。"""
    source = "argument"
    key = (api_key or "").strip() or None
    if not key:
        key = first_env(API_KEY_ENV_VARS)
        source = "env" if key else "none"

    url = base_url or first_env(BASE_URL_ENV_VARS)

    if use_jlwriter and (not key or not url):
        jlw_key, jlw_url = load_jlwriter_credentials()
        if jlw_key and not key:
            key = jlw_key
            source = "jlwriter"
        if jlw_url and not url:
            url = jlw_url

    resolved_url = resolve_base_url(url, workspace_id)
    return Credentials(api_key=key, base_url=resolved_url, source=source)


def resolve_model(model: Optional[str] = None) -> str:
    """模型名优先级：参数 > 环境变量 > 默认 ``qwen-image-3.0``。"""
    return (model or first_env(MODEL_ENV_VARS) or DEFAULT_MODEL).strip()
