"""Qwen-Image-3.0 生图客户端。

支持三种接入方式（同一把 API Key，同一个业务空间）：

``openai``
    百炼的 OpenAI 兼容协议，同步返回，最省事，默认使用。
    ``POST {base}/compatible-mode/v1/images/generations``
``dashscope``
    DashScope 原生同步协议，参数结构为 ``input`` / ``parameters``。
    ``POST {base}/api/v1/services/aigc/multimodal-generation/generation``
``async``
    DashScope 异步协议：先提交任务拿 ``task_id``，再轮询结果，
    适合批量出图或不想长时间占用连接。
    ``POST {base}/api/v1/services/aigc/image-generation/generation``

三种方式返回同一套 :class:`GeneratedImage`，上层不用关心协议差异。
"""
from __future__ import annotations

import base64
import os
import random
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import requests

from .config import DEFAULT_PROTOCOL, resolve_credentials, resolve_model
from .errors import (
    QwenImageAuthError,
    QwenImageConfigError,
    QwenImageConnectionError,
    QwenImageRateLimitError,
    QwenImageRequestError,
    QwenImageResponseError,
    QwenImageServerError,
    QwenImageTaskFailed,
    QwenImageTimeout,
    QwenImageValidationError,
)
from .presets import (
    DEFAULT_HEIGHT,
    DEFAULT_WIDTH,
    Preset,
    compose_prompt,
    default_negative,
    parse_size,
    resolve_preset,
    size_to_string,
    validate_size,
)
from .storage import (
    build_stem,
    convert_image,
    ensure_dir,
    ensure_image_bytes,
    now_iso,
    unique_path,
    write_sidecar,
)

__version__ = "1.0.0"

PROTOCOLS: Tuple[str, ...] = ("openai", "dashscope", "async")
RETRY_STATUS_CODES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
_KNOWN_SUFFIXES = ("/compatible-mode/v1", "/compatible-mode", "/api/v1")


# ------------------------------------------------------------------ 数据结构
@dataclass
class ImageRequest:
    """一次生图请求（已经过本地校验与提示词拼装）。"""

    prompt: str
    negative_prompt: str = ""
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    n: int = 1
    seed: Optional[int] = None
    images: List[str] = field(default_factory=list)
    prompt_extend: bool = True
    prompt_extend_mode: str = "direct"
    enable_thinking: bool = False
    watermark: bool = False
    # 以下字段只用于本地记录，不会发送给服务端
    subject: str = ""
    preset_name: Optional[str] = None
    style: Optional[str] = None

    def size_str(self, separator: str = "x") -> str:
        return size_to_string(self.width, self.height, separator)

    def to_openai_payload(self, model: str) -> Dict[str, Any]:
        """OpenAI 兼容协议：参数全部放在请求体顶层。"""
        body: Dict[str, Any] = {
            "model": model,
            "prompt": self.prompt,
            "size": self.size_str("x"),
            "n": self.n,
            "prompt_extend": self.prompt_extend,
            "watermark": self.watermark,
        }
        if _is_qwen_30(model):
            body["prompt_extend_mode"] = self.prompt_extend_mode
            body["enable_thinking"] = self.enable_thinking
        if self.negative_prompt and not _is_qwen_21(model):
            body["negative_prompt"] = self.negative_prompt
        if self.seed is not None:
            body["seed"] = self.seed
        if self.images:
            body["image"] = self.images[0] if len(self.images) == 1 else list(self.images)
        return body

    def to_dashscope_payload(self, model: str) -> Dict[str, Any]:
        """DashScope 协议：``input.messages`` + ``parameters``。"""
        content: List[Dict[str, Any]] = [{"image": item} for item in self.images]
        content.append({"text": self.prompt})
        parameters: Dict[str, Any] = {
            "size": self.size_str("*"),
            "n": self.n,
            "prompt_extend": self.prompt_extend,
            "watermark": self.watermark,
        }
        if _is_qwen_30(model):
            parameters["prompt_extend_mode"] = self.prompt_extend_mode
            parameters["enable_thinking"] = self.enable_thinking
        if self.negative_prompt and not _is_qwen_21(model):
            parameters["negative_prompt"] = self.negative_prompt
        if self.seed is not None:
            parameters["seed"] = self.seed
        return {
            "model": model,
            "input": {"messages": [{"role": "user", "content": content}]},
            "parameters": parameters,
        }


@dataclass
class GeneratedImage:
    """一张生成结果。"""

    url: Optional[str] = None
    b64: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    request_id: Optional[str] = None
    task_id: Optional[str] = None
    model: str = ""
    prompt: str = ""
    negative_prompt: str = ""
    size: str = ""
    seed: Optional[int] = None
    protocol: str = ""
    revised_prompt: Optional[str] = None
    usage: Dict[str, Any] = field(default_factory=dict)
    local_path: Optional[str] = None
    metadata_path: Optional[str] = None
    created_at: str = field(default_factory=now_iso)
    elapsed_s: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "size": self.size,
            "seed": self.seed,
            "model": self.model,
            "protocol": self.protocol,
            "request_id": self.request_id,
            "task_id": self.task_id,
            "revised_prompt": self.revised_prompt,
            "local_path": self.local_path,
            "metadata_path": self.metadata_path,
            "created_at": self.created_at,
            "elapsed_s": self.elapsed_s,
            "usage": self.usage,
        }


# ------------------------------------------------------------------ 参数校验 / 拼装
def _validate_common(
    prompt: str,
    n: int,
    seed: Optional[int],
    prompt_extend: bool,
    prompt_extend_mode: str,
    enable_thinking: bool,
    images: Sequence[str],
) -> None:
    if not (prompt or "").strip():
        raise QwenImageValidationError("提示词不能为空")
    if not isinstance(n, int) or isinstance(n, bool) or not 1 <= n <= 6:
        raise QwenImageValidationError(f"n 必须是 1~6 的整数，当前为 {n!r}")
    if seed is not None:
        if not isinstance(seed, int) or isinstance(seed, bool):
            raise QwenImageValidationError(f"seed 必须是整数，当前为 {seed!r}")
        if not 0 <= seed <= 2_147_483_647:
            raise QwenImageValidationError("seed 取值范围为 0 ~ 2147483647")
    if prompt_extend_mode not in ("direct", "agent"):
        raise QwenImageValidationError(
            f"prompt_extend_mode 只能是 direct 或 agent，当前为 {prompt_extend_mode!r}"
        )
    if prompt_extend_mode == "agent" and images:
        raise QwenImageValidationError("prompt_extend_mode=agent 仅支持文生图，不能搭配参考图")
    if enable_thinking and not prompt_extend:
        raise QwenImageValidationError("enable_thinking 需要同时开启 prompt_extend")
    for item in images:
        if not isinstance(item, str) or not item.strip():
            raise QwenImageValidationError("参考图必须是 URL 或 data URI 字符串")


def build_request(
    prompt: str,
    *,
    preset: Union[str, Preset, None] = None,
    style: Optional[str] = None,
    size: Union[str, Sequence[int], None] = None,
    negative_prompt: Optional[str] = None,
    n: int = 1,
    seed: Optional[int] = None,
    images: Optional[Sequence[str]] = None,
    prompt_extend: bool = True,
    prompt_extend_mode: str = "direct",
    enable_thinking: bool = False,
    watermark: bool = False,
    allow_text: bool = False,
    include_hint: bool = True,
) -> ImageRequest:
    """拼装并校验一次请求，不发送网络调用。"""
    subject = (prompt or "").strip()
    preset_obj = resolve_preset(preset)
    composed = compose_prompt(
        subject, style=style, preset=preset_obj, include_hint=include_hint
    )

    if size is not None:
        parsed = parse_size(size)
        if parsed is None:
            raise QwenImageValidationError(
                f"无法解析尺寸 {size!r}，请使用 1024x1024 或 [1024, 1024]"
            )
        width, height = parsed
    elif preset_obj is not None:
        width, height = preset_obj.size
    else:
        width, height = DEFAULT_WIDTH, DEFAULT_HEIGHT
    validate_size(width, height)

    image_list = [str(item).strip() for item in (images or []) if str(item).strip()]
    _validate_common(
        composed, n, seed, prompt_extend, prompt_extend_mode, enable_thinking, image_list
    )

    if negative_prompt is None:
        negative = default_negative(preset_obj, allow_text=allow_text)
    else:
        negative = negative_prompt.strip()

    return ImageRequest(
        prompt=composed,
        negative_prompt=negative,
        width=width,
        height=height,
        n=n,
        seed=seed,
        images=image_list,
        prompt_extend=prompt_extend,
        prompt_extend_mode=prompt_extend_mode,
        enable_thinking=enable_thinking,
        watermark=watermark,
        subject=subject,
        preset_name=preset_obj.name if preset_obj else None,
        style=style,
    )


# ------------------------------------------------------------------ 客户端
class QwenImageClient:
    """向 Qwen-Image-3.0 发送生图请求。

    参数
    ----
    api_key:
        百炼 API Key。缺省时依次读取 ``QWEN_IMAGE_API_KEY``、
        ``DASHSCOPE_API_KEY``、``QWEN_API_KEY``。
    base_url:
        服务接入点。默认 ``https://dashscope.aliyuncs.com``；也可传入
        ``https://{workspace_id}.cn-beijing.maas.aliyuncs.com`` 这类业务空间域名。
    protocol:
        ``openai``（默认）/ ``dashscope`` / ``async``。
    """

    PROTOCOLS = PROTOCOLS

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        workspace_id: Optional[str] = None,
        model: Optional[str] = None,
        protocol: str = DEFAULT_PROTOCOL,
        timeout: Union[float, Tuple[float, float]] = (10.0, 300.0),
        max_retries: int = 2,
        poll_interval: float = 2.0,
        poll_timeout: float = 300.0,
        session: Optional[requests.Session] = None,
        use_jlwriter_key: bool = False,
        user_agent: Optional[str] = None,
    ) -> None:
        credentials = resolve_credentials(
            api_key=api_key,
            base_url=base_url,
            workspace_id=workspace_id,
            use_jlwriter=use_jlwriter_key,
        )
        self.api_key = credentials.api_key
        self.base_url = credentials.base_url
        self.credential_source = credentials.source

        self.model = resolve_model(model)
        normalized_protocol = (protocol or DEFAULT_PROTOCOL).strip().lower()
        if normalized_protocol not in PROTOCOLS:
            raise QwenImageValidationError(
                f"protocol 只能是 {' / '.join(PROTOCOLS)}，当前为 {protocol!r}"
            )
        self.protocol = normalized_protocol

        self.timeout = _normalize_timeout(timeout)
        self.max_retries = max(0, int(max_retries))
        self.poll_interval = max(0.01, float(poll_interval))
        self.poll_timeout = max(1.0, float(poll_timeout))
        self.user_agent = user_agent or f"qwen-image-plugin/{__version__}"

        self._session = session or requests.Session()
        self._sleep = time.sleep
        self._random = random.random
        self._last_request_id: Optional[str] = None

    # ---------------------------------------------------------- 上下文管理
    def close(self) -> None:
        try:
            self._session.close()
        except Exception:  # pragma: no cover - 关闭失败无需中断调用方
            pass

    def __enter__(self) -> "QwenImageClient":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    # ---------------------------------------------------------- 地址
    def _root_url(self) -> str:
        url = self.base_url.rstrip("/")
        for suffix in _KNOWN_SUFFIXES:
            if url.endswith(suffix):
                url = url[: -len(suffix)]
                break
        return url.rstrip("/")

    @property
    def openai_endpoint(self) -> str:
        return f"{self._root_url()}/compatible-mode/v1/images/generations"

    @property
    def dashscope_endpoint(self) -> str:
        return f"{self._root_url()}/api/v1/services/aigc/multimodal-generation/generation"

    @property
    def async_endpoint(self) -> str:
        return f"{self._root_url()}/api/v1/services/aigc/image-generation/generation"

    def task_endpoint(self, task_id: str) -> str:
        return f"{self._root_url()}/api/v1/tasks/{task_id}"

    def endpoint_for(self, protocol: Optional[str] = None) -> str:
        protocol = (protocol or self.protocol).lower()
        if protocol == "openai":
            return self.openai_endpoint
        if protocol == "dashscope":
            return self.dashscope_endpoint
        if protocol == "async":
            return self.async_endpoint
        raise QwenImageValidationError(f"未知协议：{protocol!r}")

    # ---------------------------------------------------------- 请求描述
    def describe_request(
        self, request: ImageRequest, model: Optional[str] = None
    ) -> Dict[str, Any]:
        """返回 ``{protocol, endpoint, headers, body}``，不含 Authorization。

        用于 ``--dry-run``、日志与联调，不会发起网络请求。
        """
        model = model or self.model
        if self.protocol == "openai":
            body = request.to_openai_payload(model)
        else:
            body = request.to_dashscope_payload(model)
        headers = {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
        }
        if self.protocol == "async":
            headers["X-DashScope-Async"] = "enable"
        return {
            "protocol": self.protocol,
            "endpoint": self.endpoint_for(),
            "headers": headers,
            "body": body,
        }

    # ---------------------------------------------------------- 生图入口
    def generate(
        self,
        prompt: str,
        *,
        preset: Union[str, Preset, None] = None,
        style: Optional[str] = None,
        size: Union[str, Sequence[int], None] = None,
        negative_prompt: Optional[str] = None,
        n: int = 1,
        seed: Optional[int] = None,
        images: Optional[Sequence[str]] = None,
        prompt_extend: bool = True,
        prompt_extend_mode: str = "direct",
        enable_thinking: bool = False,
        watermark: bool = False,
        allow_text: bool = False,
        include_hint: bool = True,
        model: Optional[str] = None,
    ) -> List[GeneratedImage]:
        """生成图片并返回结果列表（默认不下载，只拿到 URL）。"""
        request = build_request(
            prompt,
            preset=preset,
            style=style,
            size=size,
            negative_prompt=negative_prompt,
            n=n,
            seed=seed,
            images=images,
            prompt_extend=prompt_extend,
            prompt_extend_mode=prompt_extend_mode,
            enable_thinking=enable_thinking,
            watermark=watermark,
            allow_text=allow_text,
            include_hint=include_hint,
        )
        model = model or self.model
        started = time.monotonic()

        if self.protocol == "openai":
            data = self._request_json(
                "POST",
                self.openai_endpoint,
                body=request.to_openai_payload(model),
                headers=self._headers(),
                retries=self.max_retries,
            )
            images_out = self._parse_openai(data, request, model)
        elif self.protocol == "dashscope":
            data = self._request_json(
                "POST",
                self.dashscope_endpoint,
                body=request.to_dashscope_payload(model),
                headers=self._headers(),
                retries=self.max_retries,
            )
            images_out = self._parse_dashscope(data, request, model)
        else:
            submit_headers = self._headers({"X-DashScope-Async": "enable"})
            data = self._request_json(
                "POST",
                self.async_endpoint,
                body=request.to_dashscope_payload(model),
                headers=submit_headers,
                retries=self.max_retries,
            )
            images_out = self._parse_async(data, request, model)

        elapsed = time.monotonic() - started
        for image in images_out:
            image.elapsed_s = round(elapsed, 2)
            if image.seed is None:
                image.seed = request.seed
        return images_out

    def generate_to_dir(
        self,
        prompt: str,
        out_dir: Union[str, Path] = "assets/images",
        *,
        name: Optional[str] = None,
        ext: str = "png",
        quality: int = 88,
        preset: Union[str, Preset, None] = None,
        style: Optional[str] = None,
        size: Union[str, Sequence[int], None] = None,
        negative_prompt: Optional[str] = None,
        n: int = 1,
        seed: Optional[int] = None,
        images: Optional[Sequence[str]] = None,
        prompt_extend: bool = True,
        prompt_extend_mode: str = "direct",
        enable_thinking: bool = False,
        watermark: bool = False,
        allow_text: bool = False,
        include_hint: bool = True,
        model: Optional[str] = None,
    ) -> List[GeneratedImage]:
        """生成、下载到本地，并写出同名 ``.json`` 元数据。"""
        request = build_request(
            prompt,
            preset=preset,
            style=style,
            size=size,
            negative_prompt=negative_prompt,
            n=n,
            seed=seed,
            images=images,
            prompt_extend=prompt_extend,
            prompt_extend_mode=prompt_extend_mode,
            enable_thinking=enable_thinking,
            watermark=watermark,
            allow_text=allow_text,
            include_hint=include_hint,
        )
        generated = self.generate(
            prompt,
            preset=preset,
            style=style,
            size=size,
            negative_prompt=negative_prompt,
            n=n,
            seed=seed,
            images=images,
            prompt_extend=prompt_extend,
            prompt_extend_mode=prompt_extend_mode,
            enable_thinking=enable_thinking,
            watermark=watermark,
            allow_text=allow_text,
            include_hint=include_hint,
            model=model,
        )

        target_dir = ensure_dir(Path(out_dir))
        model_name = model or self.model
        ext = (ext or "png").lower().lstrip(".")
        results: List[GeneratedImage] = []
        total = len(generated)
        for index, image in enumerate(generated, start=1):
            stem = build_stem(
                request.subject or request.prompt,
                request.preset_name,
                image.seed if image.seed is not None else seed,
                name=name,
                index=index if total > 1 else None,
            )
            downloaded = self.download(image, unique_path(target_dir / f"{stem}.png"))
            final_path = downloaded
            if ext not in ("png", ""):
                final_path = convert_image(
                    downloaded,
                    ext,
                    quality=quality,
                    target=unique_path(downloaded.with_suffix("." + ext)),
                )
            image.local_path = str(final_path)
            metadata = self._metadata(image, request, model_name)
            image.metadata_path = str(write_sidecar(final_path, metadata))
            results.append(image)
        return results

    # ---------------------------------------------------------- 下载
    def download(self, image: GeneratedImage, path: Union[str, Path]) -> Path:
        """把结果保存到 ``path``，返回实际写入的路径。"""
        if image.b64:
            payload = image.b64
            if payload.startswith("data:"):
                payload = payload.split(",", 1)[-1]
            try:
                data = base64.b64decode(payload)
            except Exception as exc:
                raise QwenImageResponseError(f"base64 图片解码失败：{exc}") from exc
            source = "base64 结果"
        else:
            if not image.url:
                raise QwenImageResponseError("结果里既没有 url 也没有 b64 数据")
            data = self._download_bytes(image.url)
            source = image.url

        fmt = ensure_image_bytes(data, source)
        actual = "jpg" if fmt == "jpeg" else fmt
        target = Path(path)
        if target.suffix.lower().lstrip(".") != actual:
            target = unique_path(target.with_suffix("." + actual))
        target.parent.mkdir(parents=True, exist_ok=True)

        temp = target.with_name(target.name + ".part")
        temp.write_bytes(data)
        os.replace(temp, target)
        image.local_path = str(target)
        return target

    # ---------------------------------------------------------- 内部：HTTP
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        if not self.api_key:
            raise QwenImageConfigError(
                "缺少 API Key：请设置环境变量 DASHSCOPE_API_KEY（或 QWEN_IMAGE_API_KEY），"
                "或传入 --api-key，或加 --use-jlwriter-key 复用 JLwriter 已保存的 Key。"
            )
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "User-Agent": self.user_agent,
        }
        if extra:
            headers.update(extra)
        return headers

    def _backoff(self, attempt: int) -> float:
        return min(2.0 ** attempt, 8.0) + self._random() * 0.3

    def _retry_after(self, response: requests.Response, attempt: int) -> float:
        value = response.headers.get("Retry-After")
        if value:
            try:
                return max(0.0, float(value))
            except ValueError:
                pass
        return self._backoff(attempt)

    def _request_json(
        self,
        method: str,
        url: str,
        *,
        body: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
        retries: Optional[int] = None,
    ) -> Dict[str, Any]:
        attempts = (self.max_retries if retries is None else max(0, retries)) + 1
        last_error: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                response = self._session.request(
                    method,
                    url,
                    json=body,
                    headers=headers or self._headers(),
                    timeout=self.timeout,
                )
            except requests.Timeout as exc:
                last_error = exc
                if attempt == attempts - 1:
                    raise QwenImageTimeout(
                        f"请求超时（{self.timeout[-1]} 秒）：{url}"
                    ) from exc
                self._sleep(self._backoff(attempt))
                continue
            except requests.RequestException as exc:
                last_error = exc
                if attempt == attempts - 1:
                    raise QwenImageConnectionError(
                        f"网络请求失败：{exc}"
                    ) from exc
                self._sleep(self._backoff(attempt))
                continue

            if response.status_code in RETRY_STATUS_CODES and attempt < attempts - 1:
                self._sleep(self._retry_after(response, attempt))
                continue

            if response.status_code >= 400:
                self._raise_for_status(response)

            try:
                payload = response.json()
            except ValueError as exc:
                snippet = (response.text or "")[:200]
                raise QwenImageResponseError(
                    f"响应不是合法 JSON（HTTP {response.status_code}）：{snippet!r}"
                ) from exc
            self._last_request_id = response.headers.get("x-request-id")
            return payload

        raise QwenImageConnectionError(f"重试 {attempts} 次后仍失败：{last_error}")

    def _download_bytes(self, url: str) -> bytes:
        attempts = self.max_retries + 1
        for attempt in range(attempts):
            try:
                response = self._session.get(
                    url, timeout=self.timeout, stream=True
                )
            except requests.Timeout as exc:
                if attempt == attempts - 1:
                    raise QwenImageTimeout(f"下载图片超时：{url}") from exc
                self._sleep(self._backoff(attempt))
                continue
            except requests.RequestException as exc:
                if attempt == attempts - 1:
                    raise QwenImageConnectionError(f"下载图片失败：{exc}") from exc
                self._sleep(self._backoff(attempt))
                continue

            if response.status_code in RETRY_STATUS_CODES and attempt < attempts - 1:
                self._sleep(self._retry_after(response, attempt))
                continue
            if response.status_code >= 400:
                raise QwenImageServerError(
                    f"下载图片失败（HTTP {response.status_code}）：{url}",
                    status_code=response.status_code,
                )
            return response.content
        raise QwenImageConnectionError(f"下载图片重试 {attempts} 次后仍失败：{url}")

    def _raise_for_status(self, response: requests.Response) -> None:
        body: Dict[str, Any] = {}
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                body = parsed
        except ValueError:
            body = {}

        error = body.get("error") if isinstance(body.get("error"), dict) else {}
        message = (
            error.get("message")
            or body.get("message")
            or f"HTTP {response.status_code} {response.reason or ''}".strip()
        )
        code = error.get("code") or body.get("code") or error.get("type")
        request_id = body.get("request_id") or response.headers.get("x-request-id")
        status = response.status_code

        kwargs = {
            "code": code,
            "status_code": status,
            "request_id": request_id,
            "body": body,
        }
        if status in (401, 403):
            raise QwenImageAuthError(
                f"鉴权失败：{message}（请确认 API Key 与 base_url 属于同一地域/业务空间）"
                if status == 401
                else f"无权调用该模型：{message}",
                **kwargs,
            )
        if status == 429:
            raise QwenImageRateLimitError(f"触发限流：{message}", **kwargs)
        if status >= 500:
            raise QwenImageServerError(f"服务端错误：{message}", **kwargs)
        raise QwenImageRequestError(f"请求不被接受：{message}", **kwargs)

    # ---------------------------------------------------------- 内部：响应解析
    def _parse_openai(
        self, data: Dict[str, Any], request: ImageRequest, model: str
    ) -> List[GeneratedImage]:
        items = data.get("data")
        if not isinstance(items, list) or not items:
            raise QwenImageResponseError("响应缺少 data 数组", body=data)
        usage = data.get("usage") or {}
        width = usage.get("output_width") or usage.get("width") or request.width
        height = usage.get("output_height") or usage.get("height") or request.height
        request_id = data.get("request_id") or usage.get("request_id") or self._last_request_id

        images: List[GeneratedImage] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            url = item.get("url")
            b64 = item.get("b64_json")
            if not url and not b64:
                continue
            images.append(
                GeneratedImage(
                    url=url,
                    b64=b64,
                    width=width,
                    height=height,
                    size=size_to_string(width, height),
                    request_id=request_id,
                    model=model,
                    prompt=request.prompt,
                    negative_prompt=request.negative_prompt,
                    protocol="openai",
                    revised_prompt=item.get("revised_prompt"),
                    usage=usage,
                )
            )
        if not images:
            raise QwenImageResponseError("data 中没有可用的图片地址", body=data)
        return images

    def _parse_dashscope(
        self, data: Dict[str, Any], request: ImageRequest, model: str
    ) -> List[GeneratedImage]:
        output = data.get("output") or {}
        if not isinstance(output, dict):
            raise QwenImageResponseError("响应 output 字段格式异常", body=data)
        images = self._images_from_output(output, request, model, data)
        if not images:
            raise QwenImageResponseError(
                f"响应中没有图片，output={str(output)[:300]}", body=data
            )
        return images

    def _images_from_output(
        self,
        output: Dict[str, Any],
        request: ImageRequest,
        model: str,
        data: Optional[Dict[str, Any]] = None,
        protocol: str = "dashscope",
    ) -> List[GeneratedImage]:
        usage = (data or {}).get("usage") or {}
        width = usage.get("output_width") or usage.get("width") or request.width
        height = usage.get("output_height") or usage.get("height") or request.height
        request_id = (data or {}).get("request_id") or self._last_request_id
        task_id = output.get("task_id")

        images: List[GeneratedImage] = []
        for choice in output.get("choices") or []:
            message = (choice or {}).get("message") or {}
            for part in message.get("content") or []:
                if not isinstance(part, dict):
                    continue
                url = part.get("image") or part.get("url")
                if not url:
                    continue
                images.append(
                    GeneratedImage(
                        url=url,
                        width=width,
                        height=height,
                        size=size_to_string(width, height),
                        request_id=request_id,
                        task_id=task_id,
                        model=model,
                        prompt=request.prompt,
                        negative_prompt=request.negative_prompt,
                        protocol=protocol,
                        usage=usage,
                    )
                )
        return images

    def _parse_async(
        self, data: Dict[str, Any], request: ImageRequest, model: str
    ) -> List[GeneratedImage]:
        output = data.get("output") or {}
        task_id = output.get("task_id") if isinstance(output, dict) else None
        if not task_id:
            message = data.get("message") or data.get("code") or "未返回 task_id"
            raise QwenImageResponseError(f"异步任务提交失败：{message}", body=data)

        final = self._poll_task(str(task_id))
        output = final.get("output") or {}
        images = self._images_from_output(output, request, model, final, protocol="async")
        if not images:
            raise QwenImageResponseError(
                f"任务 {task_id} 已成功但没有图片：{str(output)[:300]}", body=final
            )
        for image in images:
            image.task_id = str(task_id)
        return images

    def _poll_task(self, task_id: str) -> Dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout
        interval = self.poll_interval
        while True:
            data = self._request_json(
                "GET", self.task_endpoint(task_id), retries=self.max_retries
            )
            output = data.get("output") or {}
            status = str(output.get("task_status") or "").upper()

            if status == "SUCCEEDED":
                return data
            if status in ("FAILED", "CANCELED", "UNKNOWN"):
                raise QwenImageTaskFailed(
                    f"任务 {task_id} 结束状态为 {status}："
                    f"{output.get('message') or data.get('message') or '无错误信息'}",
                    code=output.get("code") or data.get("code"),
                    request_id=data.get("request_id"),
                    body=data,
                )
            if time.monotonic() >= deadline:
                raise QwenImageTimeout(
                    f"等待任务 {task_id} 超时（{self.poll_timeout:.0f} 秒），"
                    f"最后状态 {status or '未知'}"
                )
            self._sleep(interval)
            interval = min(interval * 1.5, 8.0)

    # ---------------------------------------------------------- 内部：元数据
    def _metadata(
        self, image: GeneratedImage, request: ImageRequest, model: str
    ) -> Dict[str, Any]:
        return {
            "file": Path(image.local_path).name if image.local_path else None,
            "created_at": image.created_at,
            "model": model,
            "protocol": self.protocol,
            "prompt": request.prompt,
            "subject": request.subject,
            "negative_prompt": request.negative_prompt,
            "style": request.style,
            "preset": request.preset_name,
            "size": image.size or request.size_str(),
            "width": image.width,
            "height": image.height,
            "seed": image.seed,
            "n": request.n,
            "prompt_extend": request.prompt_extend,
            "prompt_extend_mode": request.prompt_extend_mode,
            "enable_thinking": request.enable_thinking,
            "watermark": request.watermark,
            "reference_images": list(request.images),
            "request_id": image.request_id,
            "task_id": image.task_id,
            "source_url": image.url,
            "usage": image.usage,
            "elapsed_s": image.elapsed_s,
        }


def _is_qwen_30(model: str) -> bool:
    """3.0 系列才支持 negative_prompt / prompt_extend_mode / enable_thinking。"""
    return "3.0" in (model or "") or (model or "").strip().lower().startswith("qwen-image-3")


def _is_qwen_21(model: str) -> bool:
    """qwen-image-2.1 系列不支持 negative_prompt，带了会直接 400。"""
    return (model or "").strip().lower().startswith("qwen-image-2.1")


def _normalize_timeout(
    timeout: Union[float, Tuple[float, float], Sequence[float]]
) -> Tuple[float, float]:
    if isinstance(timeout, (int, float)):
        return (10.0, float(timeout))
    if isinstance(timeout, (tuple, list)) and len(timeout) == 2:
        return (float(timeout[0]), float(timeout[1]))
    raise QwenImageValidationError("timeout 需为秒数或 (连接超时, 读取超时) 二元组")
