# 文学风 UI 设计系统（literary）

一套面向写作软件的可移植 PyQt5 控件与主题系统：**夜读 / 护眼 / 书卷** 三种模式，
纸纹、宋体、印章、细饰线，所有颜色来自令牌，所有控件只依赖 PyQt5。

![控件样张](../../../../docs/ui-preview/book-showcase.png)

## 三种主题

| 模式 | key | 气质 | 主色 | 画布 |
| --- | --- | --- | --- | --- |
| 夜读 | `night` | 墨蓝夜色 + 暖金灯火 | `#C8A464` | `#14161C` |
| 护眼 | `eye` | 青瓷纸色 + 苔绿 | `#557A5C` | `#DCE7D6` |
| 书卷 | `book` | 旧纸米色 + 朱砂印章 | `#9E3B2C` | `#F1E7D6` |

三套主题的正文对比度均 ≥ 7:1（有单元测试守护），夜间不会出现灰字压深底。

## 尺寸与缩放

界面以 **2560×1600** 为设计基准，并按屏幕逻辑分辨率自适应：

* 1280 宽 → 90%，1707 左右 → 95%，2560 宽 → 100%；
* 所有对话框显示时自动收缩到可用桌面的 94%×90%，并保证标题栏留在屏幕内；
* 复杂对话框的正文放进 `QScrollArea`，只出现滚动条，不会把窗口顶出屏幕；
* 档案类页面关闭外层滚动，左侧列表与右侧编辑器各自拥有独立滚动条；
* 视图 → 界面缩放可切换 80% / 90% / 95% / 100% / 110%，或设置环境变量
  `JLWRITER_UI_SCALE=0.8`。

## 快速开始

```python
from PyQt5.QtWidgets import QApplication
from jlwriter.ui.literary import apply_theme, FramedDialog, Field

app = QApplication([])
apply_theme(app, "book")            # night / eye / book

dlg = FramedDialog(
    title="新建书籍",
    subtitle="题签 · 为这本书写下名字",
    seal_text="藏",
    motto="一书一世界，一名一浮生",
)
dlg.add_body(Field("书名", hint="必填", required=True))
dlg.add_button("取消", dlg.reject, variant="ghost")
dlg.add_button("保存", dlg.accept, variant="primary", default=True)
dlg.exec_()
```

主程序里一行完成换肤：

```python
from jlwriter.ui.literary import install
install(app, "night")      # 应用主题 + 给旧对话框自动补题头/按钮层级
```

## 控件清单

| 控件 | 说明 |
| --- | --- |
| `LiteraryDialog` | 带纸纹与顶部饰线的 `QDialog` 替代品，不建布局，可一行替换旧类 |
| `FramedDialog` | 题头 + 内容 + 页脚的完整骨架，`add_body` / `add_button` 即用 |
| `DialogHeader` / `Ornament` / `Seal` | 宋体标题、云纹分隔、朱砂印章 |
| `Field` | 题签 + 输入 + 说明 + 错误态，`set_error()` / `clear_error()` |
| `SearchField` | 带放大镜与清除按钮的搜索框 |
| `LiteraryButton` | `primary` / `quiet` / `ghost` / `danger` / `link` 五种层级 |
| `ToggleSwitch` | 180ms 滑动动画的墨色开关 |
| `ThemeSwitcher` | 夜读 / 护眼 / 书卷三段切换器，只发信号不写配置 |
| `Card` / `Tag` / `EmptyState` | 纸卡片、标签、空状态 |

## 旧代码迁移

1. 继承 `BaseDialog` 的对话框：无需改动，`ui/base_dialog.py` 已切到 `FramedDialog`，
   自动获得新题头、按钮层级和页脚。
2. 直接继承 `QDialog` 的：把基类换成 `LiteraryDialog` 即可；首次显示时
   `skin.polish_dialog` 会自动补题头、识别“保存/取消”等按钮并设置主次层级。
3. `QMessageBox` / `QInputDialog`：全局 QSS + 事件过滤器处理，不需要改调用点。

## 主题切换与持久化

* 主窗口工具栏的 `ThemeSwitcher` 与「视图 → 主题」菜单保持同步；
* 当前主题写入 `QSettings("JLwriter", "JLwriter")` 的 `ui/theme`；
* 旧配置里的 `深色 / 白色 / 米色 / 护眼绿` 会自动迁移到新 key，旧项目打开不乱。

## 可移植性

`literary/` 目录内只 import PyQt5 与标准库，微型图标（勾选、箭头、纸纹）在运行时
用 QPainter 画到用户数据目录，因此：

* 不需要携带任何二进制素材；
* 复制整个目录到另一个 PyQt5 项目即可用（把 `jlwriter.ui.literary` 换成你的包路径）；
* 新增主题只需在 `themes.py` 里加一份 `Palette`，控件与 QSS 不用改。

```python
from dataclasses import replace
from jlwriter.ui.literary.themes import PALETTES, BOOK

PALETTES["sepia"] = replace(BOOK, key="sepia", name="赭石", accent="#8A5A2B")
```

## 设计约束

* **不覆盖正文编辑器字体**：QSS 只给 `QLineEdit` 等表单控件设字体，
  `QPlainTextEdit` 的字体仍由用户设置（这是写作软件的核心）。
* **颜色只走令牌**：业务对话框里不再写死 `#666` / `#F0F5FF`；
  语义色用 `tone="success|warning|danger"` 属性。
* **对比度可测**：`tests/test_literary_ui.py` 校验三套主题的正文/卡片对比度。
* **离线渲染**：`scripts/preview_literary_ui.py` 可生成三套主题的真实控件截图。

## 文件

```
literary/
├── themes.py       # Palette / 字体 / QPalette
├── assets.py       # 运行时绘制勾选、箭头、纸纹
├── stylesheet.py   # 全量 QSS 模板
├── controller.py   # 应用主题、广播 theme_changed
├── widgets.py      # 上述控件
├── skin.py         # 旧对话框自动修饰
└── paths.py        # 独立的用户数据目录
```
