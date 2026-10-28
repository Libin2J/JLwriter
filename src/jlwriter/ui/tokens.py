"""间距令牌。

颜色、字体与控件尺寸都在 :mod:`jlwriter.ui.literary` 中管理；这里只保留旧对话框
仍在使用的间距常量，避免二十多个文件的布局代码一起改动。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SpacingTokens:
    xs: int = 4
    sm: int = 8
    md: int = 12
    lg: int = 16
    xl: int = 24
    xxl: int = 32


SPACING = SpacingTokens()
