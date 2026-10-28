"""前端常用图片预设、风格词与提示词拼装。

Qwen-Image-3.0 对输出尺寸的约束（官方文档）：

* 像素总面积：``512*512`` ~ ``2048*2048``（262,144 ~ 4,194,304）
* 长宽比：``1:8`` ~ ``8:1``

这里给出的预设都落在合法区间内，直接用于 Web / App 资源即可。
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple, Union

from .errors import QwenImageValidationError

MIN_AREA = 512 * 512
MAX_AREA = 2048 * 2048
MAX_RATIO = 8.0

DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024

_SIZE_RE = re.compile(r"^\s*(\d{2,5})\s*[xX*×]\s*(\d{2,5})\s*$")

# 常见前端比例，用于把 2048/864 这种数字写成 21:9
_COMMON_RATIOS: Tuple[Tuple[str, float], ...] = (
    ("21:9", 21 / 9),
    ("16:9", 16 / 9),
    ("1.91:1", 1.91),
    ("3.2:1", 3.2),
    ("4:3", 4 / 3),
    ("3:4", 3 / 4),
    ("1:1", 1.0),
    ("9:16", 9 / 16),
)


@dataclass(frozen=True)
class Preset:
    """一个前端资源位预设。"""

    name: str
    width: int
    height: int
    label: str
    hint: str
    negative: str = ""

    @property
    def size(self) -> Tuple[int, int]:
        return self.width, self.height

    def size_str(self, separator: str = "x") -> str:
        return f"{self.width}{separator}{self.height}"

    @property
    def aspect(self) -> str:
        """尽量用行业习惯写法（16:9、1.91:1），对不上再退化为最简整数比。"""
        ratio = self.width / self.height
        for label, value in _COMMON_RATIOS:
            if abs(ratio - value) / value <= 0.03:
                return label
        from math import gcd

        divisor = gcd(self.width, self.height) or 1
        return f"{self.width // divisor}:{self.height // divisor}"


PRESETS: Dict[str, Preset] = {
    "hero": Preset(
        name="hero",
        width=1920,
        height=1080,
        label="首页首屏横幅（16:9）",
        hint="宽幅横版构图，主体偏右，左侧留出大块干净空间用于网页标题与按钮，背景简洁",
        negative="杂乱背景, 主体贴边, 画面拥挤",
    ),
    "hero_wide": Preset(
        name="hero_wide",
        width=2048,
        height=864,
        label="超宽横幅 / 顶部通栏（21:9）",
        hint="超宽横幅构图，元素横向延展，视觉重心居中偏右，两端留出裁切安全区",
        negative="主体贴边, 画面拥挤",
    ),
    "og": Preset(
        name="og",
        width=1200,
        height=630,
        label="社交分享卡片（1.91:1，Open Graph）",
        hint="居中构图，主体清晰突出，四周留出安全边距，适合分享卡片裁切",
        negative="主体贴边, 关键内容位于边缘",
    ),
    "card": Preset(
        name="card",
        width=1200,
        height=900,
        label="卡片 / 博客封面（4:3）",
        hint="主体居中，背景简洁干净，边缘留白，适合卡片封面",
        negative="杂乱背景, 主体贴边",
    ),
    "square": Preset(
        name="square",
        width=1024,
        height=1024,
        label="头像 / 商品方图（1:1）",
        hint="正方形构图，主体居中，背景不抢戏，边缘留白",
        negative="主体贴边, 主体被裁切",
    ),
    "portrait": Preset(
        name="portrait",
        width=1152,
        height=1536,
        label="竖版卡片 / 详情页（3:4）",
        hint="竖版构图，主体居中，上下留出安全区，背景简洁",
        negative="主体贴边",
    ),
    "mobile": Preset(
        name="mobile",
        width=1080,
        height=1920,
        label="移动端开屏 / 故事页（9:16）",
        hint="竖屏构图，视觉重心偏上，底部留出空间放置文字与按钮，避免内容贴边",
        negative="主体贴边, 重要内容位于底部",
    ),
    "banner": Preset(
        name="banner",
        width=2048,
        height=640,
        label="长条 Banner（3.2:1）",
        hint="横向长条构图，元素沿水平方向排布，避免重要内容贴边",
        negative="主体贴边, 纵向元素过多",
    ),
    "thumb": Preset(
        name="thumb",
        width=800,
        height=450,
        label="列表缩略图（16:9）",
        hint="紧凑构图，主体占比大，缩小后仍可辨认，背景干净",
        negative="细节过多, 主体过小",
    ),
    "empty_state": Preset(
        name="empty_state",
        width=1024,
        height=768,
        label="空状态插画（4:3）",
        hint="轻量插画构图，主体小巧居中偏上，四周大面积留白，氛围轻松",
        negative="画面拥挤, 复杂背景, 沉重氛围",
    ),
}


# ------------------------------------------------------------------ 风格词
STYLES: Dict[str, str] = {
    "photo": "专业摄影质感，自然柔和光线，浅景深，电影级调色，高清细节",
    "flat": "扁平化矢量插画，简洁几何形状，柔和渐变，现代 UI 设计风格",
    "3d": "3D 渲染，柔和体积光，细腻材质，干净背景，octane render 质感",
    "minimal": "极简主义，大面积留白，单一柔和渐变背景，克制配色",
    "line": "单色线稿插画，干净流畅的线条，纯色留白背景",
    "isometric": "等距视角（isometric）插画，柔和阴影，科技感配色",
    "glass": "毛玻璃拟态（glassmorphism），半透明层叠，柔和光晕，现代 UI 风格",
    "anime": "日系动漫风格，干净线条，明亮通透的色彩",
    "watercolor": "水彩插画，柔和晕染，纸张纹理，温暖色调",
    "cyberpunk": "赛博朋克风格，霓虹光效，暗色调，高对比，未来都市氛围",
}

# 默认反向词：前端素材通常不允许出现文字，否则无法直接使用。
BASE_NEGATIVE = "低分辨率, 模糊, 噪点, 压缩失真, 畸变, 多余肢体, 画面撕裂"
TEXT_NEGATIVE = "文字, 水印, 签名, 乱码字符, UI 文字"


def resolve_preset(value: Union[str, Preset, None]) -> Optional[Preset]:
    """把预设名解析为 :class:`Preset`；``None`` 原样返回。"""
    if value is None or isinstance(value, Preset):
        return value
    key = str(value).strip().lower()
    preset = PRESETS.get(key)
    if preset is None:
        available = ", ".join(PRESETS)
        raise QwenImageValidationError(f"未知预设 {value!r}，可选：{available}")
    return preset


def resolve_style(value: Optional[str]) -> Optional[str]:
    """把风格名解析为提示词片段；也允许直接传入自定义描述。"""
    if not value:
        return None
    key = str(value).strip()
    if key in STYLES:
        return STYLES[key]
    if key.lower() in STYLES:
        return STYLES[key.lower()]
    return key


def parse_size(value: Union[str, Sequence[int], None]) -> Optional[Tuple[int, int]]:
    """解析 ``"1024x1024"`` / ``"1024*1024"`` / ``[1024, 1024]``。

    无法解析时返回 ``None``；``None`` 输入返回 ``None``。
    """
    if value is None:
        return None
    if isinstance(value, (tuple, list)) and len(value) == 2:
        try:
            width, height = int(value[0]), int(value[1])
        except (TypeError, ValueError):
            return None
        return width, height
    match = _SIZE_RE.match(str(value))
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def validate_size(width: int, height: int) -> Tuple[int, int]:
    """校验输出尺寸是否满足 Qwen-Image-3.0 的限制。"""
    if width <= 0 or height <= 0:
        raise QwenImageValidationError(f"尺寸必须为正整数：{width}x{height}")
    area = width * height
    if area < MIN_AREA:
        raise QwenImageValidationError(
            f"尺寸 {width}x{height} 太小：像素总面积需 ≥ {MIN_AREA}（512x512）"
        )
    if area > MAX_AREA:
        raise QwenImageValidationError(
            f"尺寸 {width}x{height} 太大：像素总面积需 ≤ {MAX_AREA}（2048x2048）"
        )
    ratio = max(width, height) / min(width, height)
    if ratio > MAX_RATIO:
        raise QwenImageValidationError(
            f"尺寸 {width}x{height} 长宽比 {ratio:.2f}:1 超过上限 8:1"
        )
    return width, height


def size_to_string(width: int, height: int, separator: str = "x") -> str:
    """协议相关的尺寸字符串：OpenAI 用 ``x``，DashScope 用 ``*``。"""
    return f"{width}{separator}{height}"


# ------------------------------------------------------------------ 提示词
_PUNCT = "。．.，,、；;！!？? \t\r\n"


def _clean_clause(text: Optional[str]) -> str:
    return (text or "").strip().strip(_PUNCT)


def compose_prompt(
    subject: str,
    *,
    style: Optional[str] = None,
    preset: Optional[Preset] = None,
    include_hint: bool = True,
) -> str:
    """把用户描述、风格词、构图提示拼成最终提示词。"""
    clauses: List[str] = []
    base = _clean_clause(subject)
    if base:
        clauses.append(base)
    style_clause = _clean_clause(resolve_style(style))
    if style_clause:
        clauses.append(style_clause)
    if preset is not None and include_hint:
        hint = _clean_clause(preset.hint)
        if hint:
            clauses.append(hint)
    return "，".join(clauses)


def default_negative(
    preset: Optional[Preset] = None,
    *,
    allow_text: bool = False,
) -> str:
    """默认反向提示词；``allow_text=True`` 时不排斥文字。"""
    parts: List[str] = []
    for chunk in (BASE_NEGATIVE, preset.negative if preset else ""):
        for item in str(chunk).split(","):
            item = item.strip()
            if item and item not in parts:
                parts.append(item)
    if not allow_text:
        for item in TEXT_NEGATIVE.split(","):
            item = item.strip()
            if item and item not in parts:
                parts.append(item)
    return ", ".join(parts)


def list_presets() -> List[Preset]:
    """按定义顺序返回全部预设。"""
    return list(PRESETS.values())


def format_preset_table() -> str:
    """供 CLI ``presets`` 命令输出的对齐表格。"""
    rows = [("名称", "尺寸", "比例", "说明")]
    for preset in list_presets():
        rows.append(
            (
                preset.name,
                preset.size_str(),
                preset.aspect,
                preset.label,
            )
        )
    # 中文按两个字符宽度对齐
    def visual_len(text: str) -> int:
        return sum(2 if ord(ch) > 127 else 1 for ch in text)

    widths = [max(visual_len(row[i]) for row in rows) for i in range(4)]
    lines = []
    for row in rows:
        cells = []
        for index, cell in enumerate(row):
            padding = widths[index] - visual_len(cell)
            cells.append(cell + " " * max(padding, 0))
        lines.append("  ".join(cells).rstrip())
    return "\n".join(lines)
