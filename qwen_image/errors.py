"""qwen_image 插件使用的异常类型。

所有异常都继承自 :class:`QwenImageError`，调用方捕获这一个基类即可，
需要区分时再按子类分支处理。
"""
from __future__ import annotations

from typing import Any, Dict, Optional


class QwenImageError(Exception):
    """所有生图相关异常的基类。"""

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.request_id = request_id
        self.body = body or {}

    def __str__(self) -> str:  # noqa: D105 - 明确拼装上下文，便于终端排查
        parts = [self.message]
        if self.code:
            parts.append(f"code={self.code}")
        if self.status_code:
            parts.append(f"http={self.status_code}")
        if self.request_id:
            parts.append(f"request_id={self.request_id}")
        return " | ".join(parts)


class QwenImageConfigError(QwenImageError):
    """配置缺失或不合法（例如没有 API Key、base_url 不合法）。"""


class QwenImageValidationError(QwenImageError):
    """请求参数在本地校验阶段就不合法，未发送到服务端。"""


class QwenImageAuthError(QwenImageError):
    """API Key 无效或没有该模型的权限（HTTP 401/403）。"""


class QwenImageRequestError(QwenImageError):
    """服务端判定请求不合法（HTTP 400/404/422）。"""


class QwenImageRateLimitError(QwenImageError):
    """触发限流（HTTP 429），可稍后重试。"""


class QwenImageServerError(QwenImageError):
    """服务端错误（HTTP 5xx）。"""


class QwenImageConnectionError(QwenImageError):
    """网络层错误：DNS、代理、连接被重置等。"""


class QwenImageTimeout(QwenImageError):
    """请求或轮询任务超时。"""


class QwenImageResponseError(QwenImageError):
    """响应结构不符合预期（不是 JSON、缺少图片字段等）。"""


class QwenImageTaskFailed(QwenImageError):
    """异步任务以 FAILED / CANCELED 结束。"""
