"""主题所需的微型图片资源。

QSS 里的勾选、单选圆点、下拉箭头、搜索图标和纸张纹理都必须来自真实文件
（Qt 样式表不支持内联 SVG/Data URI）。这些资源在首次应用主题时用 QPainter
现场绘制到用户数据目录，随主题更换而归入不同子目录，避免 QPixmap 缓存串色。

因此插件不携带任何二进制素材，换色/换主题不会出现“旧图标”问题。
"""
from __future__ import annotations

import random
from pathlib import Path
from typing import Dict

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QImage, QPainter, QPen, QPixmap

from .paths import asset_dir
from .themes import Palette

def _assets_dir(palette: Palette) -> Path:
    folder = asset_dir() / palette.key
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def _canvas(width: int, height: int) -> QImage:
    image = QImage(width, height, QImage.Format_ARGB32_Premultiplied)
    image.fill(Qt.transparent)
    return image


def _save(image: QImage, path: Path) -> str:
    image.save(str(path), "PNG")
    return path.as_posix()


def _check(path: Path, color: str) -> str:
    image = _canvas(18, 18)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 2.2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(QPointF(4, 9.5), QPointF(8, 13.5), QPointF(15, 5))
    painter.end()
    return _save(image, path)


def _radio_dot(path: Path, color: str) -> str:
    image = _canvas(18, 18)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    painter.drawEllipse(QRectF(6.4, 6.4, 5.2, 5.2))
    painter.end()
    return _save(image, path)


def _chevron(path: Path, color: str) -> str:
    image = _canvas(10, 7)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(QPointF(1, 1.5), QPointF(5, 5.5), QPointF(9, 1.5))
    painter.end()
    return _save(image, path)


def _chevron_up(path: Path, color: str) -> str:
    image = _canvas(10, 7)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.5)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.drawPolyline(QPointF(1, 5.5), QPointF(5, 1.5), QPointF(9, 5.5))
    painter.end()
    return _save(image, path)


def _search(path: Path, color: str) -> str:
    image = _canvas(16, 16)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(color), 1.5)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawEllipse(QRectF(2.5, 2.5, 8.2, 8.2))
    painter.drawLine(QPointF(10.4, 10.4), QPointF(14, 14))
    painter.end()
    return _save(image, path)


def _texture(path: Path, palette: Palette) -> str:
    """生成 96×96 的可平铺纸纹：噪点 + 纤维，透明度极低。"""
    size = 96
    image = _canvas(size, size)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.Antialiasing, False)

    rng = random.Random(f"jlwriter-{palette.key}")
    base = QColor(palette.ink)
    alpha = max(2, palette.texture_alpha)

    # 细颗粒
    for _ in range(2200):
        tint = QColor(base)
        tint.setAlpha(rng.randint(1, alpha))
        painter.fillRect(rng.randrange(size), rng.randrange(size), 1, 1, tint)

    # 纸纤维：横向短线，营造手工纸的走向
    fiber_count = 26 if palette.texture == "paper" else 14
    for _ in range(fiber_count):
        tint = QColor(base)
        tint.setAlpha(rng.randint(2, max(3, alpha - 2)))
        pen = QPen(tint, 1)
        painter.setPen(pen)
        x = rng.randrange(size)
        y = rng.randrange(size)
        length = rng.randint(4, 14)
        if palette.texture == "fiber":
            painter.drawLine(x, y, x + length, y + rng.choice((-1, 0, 1)))
        else:
            painter.drawLine(x, y, x + length, y)

    painter.end()
    return _save(image, path)


def ensure_assets(palette: Palette) -> Dict[str, str]:
    """确保该主题的资源存在，返回 QSS 可直接引用的绝对路径。"""
    folder = _assets_dir(palette)
    return {
        "check": _check(folder / "check.png", palette.on_accent),
        "radio": _radio_dot(folder / "radio.png", palette.on_accent),
        "chevron": _chevron(folder / "chevron.png", palette.ink_muted),
        "chevron_up": _chevron_up(folder / "chevron-up.png", palette.ink_muted),
        "search": _search(folder / "search.png", palette.ink_muted),
        "texture": _texture(folder / "texture.png", palette),
    }


def theme_glyph(palette: Palette, key: str, size: int = 18) -> QPixmap:
    """给主题切换器绘制月/叶/书三种小图。"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    pen = QPen(QColor(palette.ink_muted), 1.3)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    rect = QRectF(2.5, 2.5, size - 5, size - 5)

    if key == "night":  # 弯月
        painter.setBrush(QColor(palette.ink_muted))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(rect)
        cut = QRectF(rect.x() + rect.width() * 0.32, rect.y() - 1, rect.width(), rect.height())
        painter.setBrush(QColor(palette.accent_soft))
        painter.drawEllipse(cut)
    elif key == "eye":  # 叶
        painter.drawArc(rect, 40 * 16, 220 * 16)
        painter.drawLine(
            QPointF(rect.center().x(), rect.top() + 1),
            QPointF(rect.center().x(), rect.bottom()),
        )
    else:  # 书
        painter.drawRect(QRectF(3, 3, size - 7, size - 6))
        painter.drawLine(QPointF(6, 3), QPointF(6, size - 3))
        painter.drawLine(QPointF(8.5, 7), QPointF(size - 5, 7))

    painter.end()
    return pixmap
