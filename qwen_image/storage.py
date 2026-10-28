"""落盘相关的小工具：文件名、去重、元数据、可选格式转换。

只依赖标准库；``webp`` / ``jpg`` 转换需要 Pillow，未安装时会给出明确提示。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .errors import QwenImageError, QwenImageResponseError, QwenImageValidationError


def now_iso() -> str:
    """本地时区的 ISO 8601 时间戳，例如 ``2026-10-26T16:20:31+08:00``。"""
    return datetime.now().astimezone().isoformat(timespec="seconds")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def short_hash(text: str, length: int = 8) -> str:
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:length]


def slugify(text: str, max_length: int = 48) -> str:
    """把提示词转成文件系统友好的短名。

    中文等非 ASCII 内容会被丢弃；若结果为空，则退化为 ``img-<hash>``，
    保证同一个提示词每次得到的名字稳定可复现。
    """
    raw = unicodedata.normalize("NFKD", text or "")
    ascii_text = raw.encode("ascii", "ignore").decode("ascii")
    words = re.findall(r"[a-zA-Z0-9]+", ascii_text.lower())
    slug = "-".join(words)
    if not slug:
        slug = f"img-{short_hash(text or 'image')}"
    return slug[:max_length].strip("-") or "image"


def build_stem(
    prompt: str,
    preset_name: Optional[str] = None,
    seed: Optional[int] = None,
    *,
    name: Optional[str] = None,
    index: Optional[int] = None,
) -> str:
    """生成 ``hero-home-hero-12345`` 形式的文件名主干。"""
    parts = [slugify(name or prompt)]
    if preset_name:
        parts.append(slugify(preset_name, 24))
    tag = str(seed) if seed is not None else short_hash(prompt)
    # 中文提示词会退化成 img-<hash>，此时不要再重复一遍 hash
    if tag not in parts[0]:
        parts.append(tag)
    if index is not None:
        parts.append(str(index))
    stem = "-".join(part for part in parts if part)
    return stem[:120].strip("-") or "image"


def unique_path(path: Path) -> Path:
    """避免覆盖已有文件；重名时追加 ``-2``、``-3``。"""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    counter = 2
    while True:
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


_IMAGE_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpg"),
    (b"GIF87a", "gif"),
    (b"GIF89a", "gif"),
)


def detect_image_format(data: bytes) -> Optional[str]:
    """根据文件头判断图片格式。"""
    for signature, fmt in _IMAGE_SIGNATURES:
        if data.startswith(signature):
            return fmt
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def ensure_image_bytes(data: bytes, source: str = "响应") -> str:
    """校验下载结果确实是图片，返回识别出的格式。"""
    if not data:
        raise QwenImageResponseError(f"{source} 返回了空内容")
    fmt = detect_image_format(data)
    if fmt is None:
        raise QwenImageResponseError(
            f"{source} 返回的内容不是可识别的图片（前 16 字节：{data[:16]!r}）"
        )
    return fmt


def write_json(path: Path, payload: Dict[str, Any]) -> Path:
    """原子写 JSON，避免前端或热重载读到半截文件。"""
    ensure_dir(path.parent)
    temp = path.with_name(path.name + ".part")
    with temp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(temp, path)
    return path


def write_sidecar(image_path: Path, metadata: Dict[str, Any]) -> Path:
    """在图片旁边写 ``<图片文件名>.json`` 元数据。"""
    return write_json(image_path.with_name(image_path.name + ".json"), metadata)


def relative_posix(path: Path, base: Path) -> str:
    """给 ``manifest.json`` 用的相对路径，统一使用 ``/``。"""
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def convert_image(
    source: Path,
    fmt: str,
    *,
    quality: int = 88,
    remove_source: bool = True,
    target: Optional[Path] = None,
) -> Path:
    """把 PNG 转成 ``jpg`` / ``webp``，需要 Pillow。"""
    fmt = fmt.lower().lstrip(".")
    if fmt in ("jpeg", "jpg"):
        fmt = "jpg"
    if fmt not in ("jpg", "webp"):
        raise QwenImageValidationError(f"不支持的转换目标格式：{fmt}")
    if source.suffix.lower().lstrip(".") in (fmt, "jpeg" if fmt == "jpg" else fmt):
        return source

    try:
        from PIL import Image  # type: ignore
    except ImportError as exc:  # pragma: no cover - 取决于运行环境
        raise QwenImageError(
            "转换为 jpg/webp 需要 Pillow，请先执行：pip install pillow"
        ) from exc

    target = target or source.with_suffix("." + fmt)
    target.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(source) as image:
        if fmt == "jpg":
            image.convert("RGB").save(target, "JPEG", quality=quality, optimize=True)
        else:
            image.save(target, "WEBP", quality=quality, method=6)
    if remove_source:
        try:
            source.unlink()
        except OSError:
            pass
    return target
