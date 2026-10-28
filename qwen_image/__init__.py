"""qwen_image —— 调用 Qwen-Image-3.0 生成前端图片资源的 Python 插件。

最简用法::

    from qwen_image import QwenImageClient

    client = QwenImageClient()          # 自动读取 DASHSCOPE_API_KEY
    images = client.generate_to_dir(
        "SaaS 产品首页主视觉，抽象 3D 渐变",
        "public/images",
        preset="hero",
        style="3d",
    )
    print(images[0].local_path)
"""
from __future__ import annotations

from .client import (
    GeneratedImage,
    ImageRequest,
    QwenImageClient,
    __version__,
    build_request,
)
from .config import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    DEFAULT_PROTOCOL,
    Credentials,
    resolve_credentials,
)
from .errors import (
    QwenImageAuthError,
    QwenImageConfigError,
    QwenImageConnectionError,
    QwenImageError,
    QwenImageRateLimitError,
    QwenImageRequestError,
    QwenImageResponseError,
    QwenImageServerError,
    QwenImageTaskFailed,
    QwenImageTimeout,
    QwenImageValidationError,
)
from .presets import (
    PRESETS,
    STYLES,
    Preset,
    compose_prompt,
    default_negative,
    list_presets,
    parse_size,
    validate_size,
)

__all__ = [
    "__version__",
    # 核心
    "QwenImageClient",
    "ImageRequest",
    "GeneratedImage",
    "build_request",
    # 配置
    "Credentials",
    "resolve_credentials",
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "DEFAULT_PROTOCOL",
    # 预设
    "PRESETS",
    "STYLES",
    "Preset",
    "list_presets",
    "compose_prompt",
    "default_negative",
    "parse_size",
    "validate_size",
    # 异常
    "QwenImageError",
    "QwenImageConfigError",
    "QwenImageValidationError",
    "QwenImageAuthError",
    "QwenImageRequestError",
    "QwenImageRateLimitError",
    "QwenImageServerError",
    "QwenImageConnectionError",
    "QwenImageTimeout",
    "QwenImageResponseError",
    "QwenImageTaskFailed",
]
