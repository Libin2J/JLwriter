# 界面重设计说明（文学风 · 三主题）

本次重设计覆盖 JLwriter 的全部对话框与主窗口外观。核心判断：**保留 PyQt5**。
完整的 Web 前端迁移意味着重写 20+ 个对话框的业务逻辑、线程、文件读写与桌面能力，
风险远高于收益；因此把“前端化”的部分收敛为一套独立的、可移植的设计系统，
让旧代码零改动接入，新代码用组件搭页面。

> 如果未来确实要迁到 Web，`themes.py` 里的令牌（颜色 / 字体 / 间距）可以直接
> 映射成 CSS 变量，`widgets.py` 的交互语义（题头、字段、按钮层级）也能复用；
> 但业务层的信号槽与本地文件操作仍需要单独重写，不适合和本次视觉改版混在一起。

## 一套系统，三种气质

| 模式 | key | 场景 | 关键色 |
| --- | --- | --- | --- |
| 夜读 | `night` | 深夜写作，低亮度暖字 | 墨蓝 `#14161C` / 暖金 `#C8A464` |
| 护眼 | `eye` | 长时间阅读，低蓝光 | 青瓷 `#DCE7D6` / 苔绿 `#557A5C` |
| 书卷 | `book` | 纸书质感，朱砂印章 | 旧纸 `#F1E7D6` / 朱砂 `#9E3B2C` |

正文与背景对比度均 ≥ 7:1（`tests/test_literary_ui.py` 会校验），
夜间不会出现“深灰字压深底”。纸张纹理、勾选、箭头、单选圆点都由 QPainter
在运行时绘制到用户数据目录，不依赖任何图片素材。

## 覆盖范围

| 层 | 做法 | 数量 |
| --- | --- | --- |
| `BaseDialog` 系列 | 重写基类为 `FramedDialog`，自动获得新题头 / 页脚 / 按钮层级 | 13 个 |
| 直接继承 `QDialog` 的 | 改为 `LiteraryDialog`，首次显示自动补题头、识别主次按钮 | 11 个 |
| `QMessageBox` / `QInputDialog` | 全局 QSS + 事件过滤器 + Qt 中文化 | 全部 |
| 主窗口 | 工具栏三段式主题切换器、视图菜单、字号/主题持久化、高 DPI | 1 套 |
| 手工重排版 | 新建书籍、全文搜索、用户协议、项目信息（含在上面的 11 个里） | 4 个 |

手工重排的对话框使用 `Field`、`SearchField`、`FramedDialog`、`LiteraryButton`，
其余对话框保留原业务布局，由设计系统统一换肤，降低回归风险。

## 主题切换

* 工具栏：`夜读 / 护眼 / 书卷` 三段切换器；
* 菜单：视图 → 主题；
* 默认密度按屏幕自适应：1280×800 用 90%，1707 左右用 95%，2560×1600 用 100%；
* 视图 → 界面缩放可手动切换 80% / 90% / 95% / 100% / 110%；
* 全局持久化：`QSettings("JLwriter", "JLwriter")` 的 `ui/theme` 与 `ui/scale`；
* 项目内持久化：原 `current_theme` 字段，旧值 `深色/白色/米色/护眼绿` 自动迁移。

## 可复用控件

`src/jlwriter/ui/literary/` 只依赖 PyQt5：

* `FramedDialog` / `LiteraryDialog` / `DialogHeader` / `Ornament` / `Seal`
* `Field` / `SearchField` / `LiteraryComboBox`
* `LiteraryButton`（primary / quiet / ghost / danger / link）
* `ToggleSwitch` / `ThemeSwitcher`
* `Card` / `Tag` / `EmptyState`

复制整个目录到其它 PyQt5 项目即可使用；新增主题只需在 `themes.py` 增加一份
`Palette`，QSS 与控件无需修改。详见 [literary/README.md](../src/jlwriter/ui/literary/README.md)。

## 预览

三套主题 × 六个真实对话框的截图（非效果图）：

[docs/ui-preview/index.html](ui-preview/index.html)

![书卷主题控件样张](ui-preview/book-showcase.png)

## 显示适配

初版按 1680×1280 设计，在 1280×764 逻辑分辨率（2560×1600 @200%）上会顶出屏幕。
现在以 **2560×1600** 为设计基准，并做小屏自适应：

* 默认密度按屏幕调整：1280 逻辑宽用 90%，1707 左右用 95%，2560 用 100%；
* 所有对话框显示时收缩到可用桌面的 94%×90%，并保证标题栏在屏幕内；
* 复杂对话框（AI 设置、策划、角色、章节规划等）的正文放进滚动区，窗口不再被内容
  最小高度撑大；
* 工具栏去掉重复文字标签、限制字体下拉宽度，1280 宽下不再溢出；
* 视图 → 界面缩放提供 80% / 90% / 95% / 100% / 110%，可随时调整。

## 档案页与图标修复

* **档案 tab**：`CharacterDialog` 关闭外层正文滚动，左侧列表与右侧编辑器各自使用
  独立 `QScrollArea`；tab 栏固定，不再被整页滚动带走。
* **关闭按钮**：不再使用字体里的 `✕`（宋体会缺字变方框），改为
  `LiteraryCloseButton` 自绘两条斜线，任何主题/缩放下都能辨认。
* **符号兼容**：`✓ / ◈ / ⬡ / ◐` 等改为宋体覆盖的 `√ / ◆ / ◇ / ◎`。

## 回归与验证

```bash
python -m unittest discover -s tests          # 39 项：生图插件 + 文学风 UI
python scripts/preview_literary_ui.py         # 重新生成预览
```

测试覆盖：主题对比度、旧主题名迁移、QSS/调色板生效、三套主题资源生成、
切换器信号、字段错误态、自动题头、22 个对话框的基类继承关系、截图渲染。
