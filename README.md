# JLwriter

<p align="center">
  <img src="docs/screenshots/jlwriter.png" alt="JLwriter" width="380">
</p>

<p align="center">
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.9%2B-blue.svg" alt="Python 3.9+"></a>
  <a href="https://pypi.org/project/jlwriter/"><img src="https://img.shields.io/badge/pypi-v0.1.0-green.svg" alt="PyPI"></a>
  <img src="https://img.shields.io/badge/PyQt5-5.15%2B-orange.svg" alt="PyQt5">
</p>

<p align="center">
  一款内置 GraphRAG 与多 Agent 协作的 AI 长篇小说写作助手
</p>

JLwriter 是为长篇网络小说作者打造的桌面写作工具。它把「世界观设定 → 分卷分弧 → 章节细纲 → 正文写作 → 精修打磨」串成一条完整的工作流，并通过多 Agent 协作与分层上下文注入，解决长篇小说创作中最棘手的 **设定一致性** 与 **上下文膨胀** 问题。

---

## 目录

- [核心特性](#-核心特性)
- [截图](#-截图)
- [快速开始](#-快速开始)
- [使用指南](#-使用指南)
- [配置说明](#️-配置说明)
- [进阶](#-进阶)
- [项目结构](#-项目结构)
- [常见问题](#-常见问题)
- [开发](#️-开发)
- [许可证](#-许可证)
- [致谢](#-致谢)

---

## ✨ 核心特性

### 📚 结构化的长篇管理

- **书架系统**：所有作品集中管理，支持封面、简介、按最近编辑排序
- **三层结构**：卷 → 弧 → 章，适配网络小说的实际写法
- **完整档案**：角色、地点、物品、势力、怪物，各自独立建档
- **关系网络**：角色 / 地点 / 组织 / 物品 / 怪物之间的多类型关系可视化

<p align="center">
  <img src="docs/screenshots/charater.png" alt="故事档案" width="720">
  <br>
  <em>故事档案：角色 / 地点 / 物品 / 势力 / 怪物 / 关系网络 六合一</em>
</p>

### 🤖 多 Agent 协作

| Agent | 职责 | 推荐模型 |
| --- | --- | --- |
| **策划 Agent** | 从零构建世界观、故事弧、章节规划、细纲 | 最强可用模型 |
| **写作 Agent** | 基于细纲续写正文 | 长上下文 + 创作能力强 |
| **编辑 Agent** | 精修文本、去 AI 味、提升文笔 | 文笔好、响应快 |
| **审核 Agent** | 一致性校验、规划审核、修正 | 高频调用，选便宜快的 |
| **大纲 Agent** | 从章节提取结构化大纲 | JSON 输出稳定 |
| **提取 Agent** | 从正文提取档案 | 结构化输出稳定 |

每个 Agent 可独立配置供应商、模型、System Prompt，互不干扰。

### 🧠 分层上下文（L0-L4）

针对 2 万字以上世界观的长篇小说，JLwriter 采用分层注入，避免「设定被稀释」：

| 层级 | 内容 | 是否可关 |
| --- | --- | --- |
| **L0** | 故事当前状态快照（角色位置、健康、情绪、已知秘密） | ✅ 可选 |
| **L1** | 世界硬规则（核心矛盾、背景、力量体系、势力总览） | ✅ 可选（总纲可单独关） |
| **L2** | 本章相关实体完整档案（按细纲精准加载） | — |
| **L3** | 剧情轨道（前序大纲 + 本章规划 + 后序边界） | — |
| **L4** | 正文上下文（本章已有正文 / 上一章完整正文） | — |

### 🕸️ 初步 GraphRAG

- 章节-实体索引自动维护
- 续写时基于图遍历筛选相关实体，只注入必要的档案
- 关系边带类型与时序，避免「已死角色复活」「关系提前建立」等设定崩坏

### 🎬 AI 策划（抽卡式生成）

九阶段递进生成，每一步都可单阶段重试或基于指引优化：

```
核心矛盾 → 故事背景 → 力量体系 → 故事总纲 → 关键人物
→ 主要势力 → 地图地点 → 重要物品 → 怪物设计
```

每个阶段生成后自动进入 **校验流水线**（一致性校验 → 自动修正 → 关键事实提炼），确保后续阶段不会偏离前序设定。

<p align="center">
  <img src="docs/screenshots/planner.png" alt="AI 策划" width="720">
  <br>
  <em>AI 策划：九阶段独立页面，可单阶段重试或优化</em>
</p>

### 🎨 其他实用功能

- **细纲展开**：为每一章生成场景节拍 + 需要的实体清单
- **知识库参考**：精修时可挂载 `knowledge/` 下的 AI 味去除模板与文笔模板
- **预设系统**：一键套用题材 / 主题 / 基调组合，可保存自定义预设
- **导出**：TXT / Markdown / PDF / 长图（单章）
- **历史记录**：每次保存自动快照，支持恢复
- **Prompt 查看器**：查看最近发给 LLM 的完整 prompt，便于调试与优化
- **多供应商**：DeepSeek / OpenAI / Qwen / Gemini / GLM / Claude

### 🖋 文学风界面与三套主题

- **夜读 / 护眼 / 书卷**：工具栏与「视图 → 主题」一键切换，旧主题自动迁移，设置持久化
- **全部对话框接入**：24 个对话框统一纸纹、宋体题头、印章与按钮层级，`QMessageBox` 也随主题
- **小屏友好**：以 2560×1600 为设计基准、按屏幕自适应密度，对话框自动收缩、正文可滚动；视图 → 界面缩放可选 80%~110%
- **可移植控件**：`src/jlwriter/ui/literary/` 只依赖 PyQt5，题头、字段、按钮、开关、主题切换器均可复用
- **真实控件预览**：[三套主题截图](docs/ui-preview/index.html)

![文学风控件样张](docs/ui-preview/book-showcase.png)

---

## 📸 截图

<table>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/main_window.png" alt="主窗口" width="100%">
      <br>
      <sub>主窗口：分卷 / 章节树 + 编辑器 + AI 对话</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/book_shelf.png" alt="书架" width="100%">
      <br>
      <sub>书架：封面卡片式浏览，右键设置信息</sub>
    </td>
  </tr>
  <tr>
    <td align="center" width="50%">
      <img src="docs/screenshots/chater_palnner.png" alt="章节规划" width="100%">
      <br>
      <sub>章节规划：卷 → 弧 → 章 三层拆解</sub>
    </td>
    <td align="center" width="50%">
      <img src="docs/screenshots/relation.png" alt="关系网络" width="100%">
      <br>
      <sub>关系网络：多类型节点 + 带箭头的边</sub>
    </td>
  </tr>
</table>

<p align="center">
  <img src="docs/screenshots/chat.png" alt="续写演示" width="720">
  <br>
  <em>续写流程：流式输出 → 精修 → 应用</em>
</p>

---

## 🚀 快速开始

### 环境要求

- Python ≥ 3.10
- Windows / macOS / Linux
- 至少一个 LLM 供应商的 API Key（推荐 DeepSeek 或 GLM，性价比高）

### 安装

```bash
pip install jlwriter
```

或者使用 `pipx` 隔离安装（推荐，避免污染全局环境）：

```bash
pipx install jlwriter
```

### 运行

```bash
jlwriter
```

或作为模块运行：

```bash
python -m jlwriter.main
```

### 首次配置

1. 程序启动后打开 `AI助手 → AI设置`
2. 在 **API 密钥** 标签页填写至少一个供应商的 Key
   - [DeepSeek](https://platform.deepseek.com/)
   - [GLM](https://open.bigmodel.cn/)
   - [Qwen](https://dashscope.aliyuncs.com/)
   - [OpenAI](https://platform.openai.com/)
3. 在 **Agent 配置** 标签页给每个 Agent 选择供应商与模型
4. 点击「测试此 Agent 连接」验证，保存

首次启动会弹出用户协议，说明哪些文本会发送给 AI 服务商。

---

## 🎯 使用指南

### 从零开始一部小说

1. **新建书籍**：`文件 → 新建`，填写书名、作者、简介、封面
2. **AI 策划**：`AI助手 → AI 策划`
   - 填写题材、主题、基调、长度、分卷数
   - 勾选需要生成的模块（力量体系 / 势力 / 地点 / 物品 / 怪物）
   - 点击「开始生成」，等待九阶段完成
   - 逐阶段查看，对不满意的阶段可点「重新生成本阶段」
   - 全部完成后点「接受并开始创作」
3. **故事档案完善**：`AI助手 → 查看故事档案`，手动补充或微调角色、地点、势力、关系等，本质上采用实体状态机设计
4. **章节规划**：`AI助手 → 章节规划`
   - 对每一卷点击「拆解本卷为弧」
   - 对每个弧点击「生成本弧下一批章节」（每批 8 章）
   - 选中章节，点击「展开本章细纲」生成场景节拍
5. **开始写作**：打开 AI 对话窗口，点击「续写当前章节」
6. **精修打磨**：写完一段后点击「AI 精修本章」，可选择挂载知识库参考

### 有现成设定时

`AI助手 → AI 策划` 打开时会检测到已有内容，让你选择：

- **载入已有设定**：进入工作区，逐阶段查看与优化
- **清空重新开始**：忽略现有内容，重新走一遍流程

### 写作工作流建议

```
策划（构建世界） → 档案（完善细节） → 弧拆解 → 章节规划 → 细纲展开
→ 正文续写 → 规划偏离校验 → 精修 → 保存 → 世界状态快照
```

---

## ⚙️ 配置说明

### 用户数据目录

所有作品数据保存在操作系统标准的用户数据目录，与安装位置无关：

| 系统 | 路径 |
| --- | --- |
| Windows | `%APPDATA%\jlwriter\` |
| macOS | `~/Library/Application Support/jlwriter/` |
| Linux | `~/.local/share/jlwriter/` |

可通过环境变量覆盖：

```bash
JLWRITER_DATA_DIR=D:\my_jlwriter_data jlwriter
```

### 目录结构

```
jlwriter/
├── book/                    # 所有书籍
│   └── 我的小说/
│       ├── project.json     # 项目数据
│       ├── project.json.history.json
│       ├── meta.json        # 元数据（书名、简介、封面）
│       └── cover.png
├── knowledge/               # 知识库（用户可自定义）
│   ├── ai_style.md          # AI 味去除模板
│   ├── 玄幻.md
│   └── 都市.md
└── presetting.json          # 用户自定义预设（可选）
```

### 知识库格式

`knowledge/*.md` 采用简单的分节格式，每个分节下每行一条案例：

```markdown
# 玄幻写作参考

## 人物描写
- 青年一袭白衣，眉目如刀裁斧刻，眼中却无半分暖意。
- 那老者佝偻着背，皮肤干枯如树皮，却有一双孩童般的眼睛。

## 对话描写
- "你输了。"他放下剑，语气平静得仿佛在陈述天气。

## 环境描写
- 山巅之上，云海翻涌，偶尔露出几座深色的山尖。
```

`ai_style.md` 是 AI 味去除模板，会被完整读取；其余 md 文件为文笔参考，精修时每节随机抽取若干条。

### 预设格式

`presetting.json`：

```json
{
  "version": 1,
  "presets": [
    {
      "id": "xianxia_classic",
      "icon": "🗡️",
      "name": "古典仙侠",
      "description": "东方玄幻，修仙问道",
      "genre": "东方玄幻",
      "theme": "求道与守护",
      "tone": "热血激昂",
      "target_length": "长篇",
      "volume_count": 5,
      "need_power_system": true,
      "need_organizations": true,
      "need_locations": true,
      "need_items": true,
      "need_monsters": false,
      "user_notes": "希望有完整的宗门体系..."
    }
  ]
}
```

---

## 🔧 进阶

### 分供应商的 API Key

所有 Agent 共享同一份 Key 表：一个供应商只需填一次 Key。如果不同 Agent 用不同供应商，切换 Agent 时自动使用对应的 Key。

### L1 中的故事总纲

`AI设置 → 全局设置` 中可独立控制「L1 是否包含故事总纲」。续写单章时，L3 已经覆盖前序章节与后序边界，故事总纲通常是冗余的，默认关闭可节省约 30%-50% 的上下文。

### L0 世界状态

`AI助手 → 生成当前章世界状态` 可为每章生成一份状态快照（角色位置、健康、情绪、已知秘密、未收束情节线）。开启 L0 后，续写时会自动注入上一章的状态。

### 黄金三章

`AI设置 → Agent 配置` 顶部可开启「黄金三章设计」。开启后，故事总纲生成、第一卷弧拆解、前 3 章规划、前 3 章细纲都会遵循「第 1 章抓读者，第 2 章深化冲突，第 3 章第一个小高潮」的原则。

### Prompt 查看器
<p align="center">
  <img src="docs/screenshots/prompt.png" alt="Prompt 查看器" width="480">
  <br>
  <em>prompt查看器</em>
</p>
`AI助手 → 查看最近 Prompt`（或悬浮按钮右键）可查看最近 50 次发送给 LLM 的完整 prompt（含 system 与 user，软件关闭后会清空本次缓存）。用于：

- 调试「为什么 AI 没按我要求写」
- 优化 prompt 结构
- 复制 / 导出 prompt 做对比实验

---

## 📁 项目结构

```
JLwriter/
├── src/jlwriter/
│   ├── main.py                  # 入口（def main()）
│   ├── main_window.py           # 主窗口
│   ├── paths.py                 # 路径管理（用户数据 / 包内资源）
│   ├── book_manager.py          # 书籍文件夹管理
│   ├── models.py                # 数据模型
│   ├── ai_config.py             # AI 配置
│   ├── ai_assistant.py          # LLM 请求线程（流式）
│   ├── agents.py                # Agent 定义
│   ├── planner_agent.py         # 策划、弧拆解、章节生成 prompt
│   ├── reviewer_agent.py        # 审核、修正 prompt
│   ├── detailed_outliner.py     # 细纲展开
│   ├── character_extractor.py   # 档案提取
│   ├── character_index.py       # 章节-实体索引与筛选
│   ├── context_builder.py       # L0-L4 分层上下文组装
│   ├── graph_builder.py         # NetworkX 图构建
│   ├── graph_query.py           # 子图查询
│   ├── world_state_builder.py   # L0 世界状态生成
│   ├── knowledge_manager.py     # 知识库读取
│   ├── preset_loader.py         # 预设加载
│   ├── exporter.py              # 导出（TXT / MD / PDF / 图片）
│   ├── prompt_history.py        # Prompt 历史记录
│   ├── ui/                      # 设计系统
│   ├── knowledge/               # 内置知识库示例
│   ├── ico/                     # 图标
│   └── presetting.json          # 内置预设
├── pyproject.toml
├── README.md
└── LICENSE
```

---

## ❓ 常见问题

### Q：启动时报 `ModuleNotFoundError: No module named 'xxx'`

检查是否通过 `pip install` 安装，而不是直接 `python main.py`。本项目采用标准包结构，不支持脚本直接运行。如需从源码运行，请使用 `python -m jlwriter.main`。

### Q：AI 返回内容被截断

在 AI 设置中调大对应 Agent 的 `max_tokens`。章节规划时若一次性生成整弧超过模型输出上限，改为分批生成。

### Q：续写时经常出现设定矛盾

检查：

1. 是否在「AI 设置 → 全局设置」中开启了 L1
2. 是否为相关章节展开了细纲（细纲会精准加载实体档案）
3. 是否开启了 L0 世界状态（尤其对涉及角色状态变化的章节）

### Q：如何删除某本书

书架中右键书籍 → 删除书籍，会移除整个文件夹。建议先备份 `book/<书名>/`。

### Q：想用本地模型（Ollama / vLLM）

AI 设置中选择「OpenAI」，把 base_url 改为本地服务的地址（如 `http://localhost:11434/v1`），模型名填本地模型名。任何 OpenAI 兼容协议的服务都可以这样接入。

### Q：API 调用费用太高

- 让高频调用的 Agent（审核 / 提取 / 大纲）使用便宜快速的模型
- 仅在关键章节（卷首、卷末、转折章）开启 L0 和完整 L1
- 关闭「L1 中包含故事总纲」
- 精修时选择不挂载知识库

---

## 🖼 Qwen-Image 生图插件（可选）

仓库根目录附带一个独立的 Python 插件 `qwen_image/`，调用 **Qwen-Image-3.0** 生成前端开发用的图片资源
（首屏主视觉、OG 分享卡片、空状态插画等），自动下载落盘并附带元数据，可直接被 `public/` 引用。
它不参与主程序运行，也可以单独复制到其它项目：

```bash
python -m qwen_image presets
python -m qwen_image generate "登录页背景，柔和蓝紫渐变" --preset hero --style minimal
python -m qwen_image batch qwen_image/examples/assets.example.json --jobs 3
```

API Key 默认读 `DASHSCOPE_API_KEY`；与桌面应用同机时，可直接加 `--use-jlwriter-key`
复用已保存的 Qwen Key 和业务空间域名。详细说明见 [qwen_image/README.md](qwen_image/README.md)。

---

## 🛠 开发

### 本地开发

```bash
git clone https://gitee.com/libin2jiang/jlwriter.git
cd jlwriter
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 运行

```bash
python -m jlwriter.main
```

或打包后：

```bash
python -m build
pip install dist/*.whl
jlwriter
```

### 贡献

欢迎提 Issue 与 PR。提交 PR 前请：

1. 确认代码在 Windows / macOS / Linux 至少一个平台能跑通
2. 新增功能时同步更新 README
3. 提交信息遵循 [Conventional Commits](https://www.conventionalcommits.org/)

---

## 📄 许可证

本项目采用 [MIT License](LICENSE) 开源。

---

## 🙏 致谢

- [PyQt5](https://riverbankcomputing.com/software/pyqt/)：桌面 UI 框架
- [OpenAI Python SDK](https://github.com/openai/openai-python)：统一的多供应商 LLM 客户端
- [NetworkX](https://networkx.org/)：图结构处理
- [json-repair](https://github.com/mangiucugr/JSON_Repair)：LLM 输出的 JSON 修复
- 所有在 Issue、讨论区提供反馈的作者朋友们

---

<p align="center">
  如果这个项目对你有帮助，欢迎点个 ⭐ Star
</p>