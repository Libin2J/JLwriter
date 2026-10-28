# qwen_image —— 前端图片生成插件

一个零框架依赖的 Python 插件：把一句文案变成可直接放进 `public/` 的图片资源。
底层调用阿里云百炼 **Qwen-Image-3.0**（`qwen-image-3.0` / `qwen-image-3.0-pro`），
内置前端常用尺寸预设、风格词、下载落盘与元数据，既能命令行批量出图，也能在 Python 里当库用。

```
qwen_image/
├── client.py     # QwenImageClient：三种协议、重试、轮询、下载
├── config.py     # Key / 接入点 / 模型解析，可复用 JLwriter 的配置
├── presets.py    # 尺寸预设、风格词、提示词拼装与校验
├── storage.py    # 文件名、去重、元数据、可选 webp/jpg 转换
├── cli.py        # python -m qwen_image
└── examples/     # 批量清单示例
```

## 1. 安装

```bash
pip install requests          # 唯一必需依赖
pip install pillow            # 可选：需要输出 webp / jpg 时再装
```

插件本身无需安装，把 `qwen_image/` 目录放到项目根目录（或任意在 `sys.path` 里的位置）即可：

```bash
python -m qwen_image --help
```

## 2. 配置

优先级：**命令行参数 > 环境变量 > JLwriter 已保存的配置（需显式开启）**。

| 环境变量 | 说明 |
| --- | --- |
| `DASHSCOPE_API_KEY` | 百炼 API Key（也接受 `QWEN_IMAGE_API_KEY`、`QWEN_API_KEY`） |
| `QWEN_IMAGE_BASE_URL` | 接入点，默认 `https://dashscope.aliyuncs.com` |
| `QWEN_IMAGE_MODEL` | 模型名，默认 `qwen-image-3.0` |
| `QWEN_IMAGE_WORKSPACE_ID` | 业务空间 ID，用于 `https://{workspace_id}.cn-beijing.maas.aliyuncs.com` |

```powershell
# PowerShell
$env:DASHSCOPE_API_KEY = "sk-xxxx"
$env:QWEN_IMAGE_BASE_URL = "https://ws-xxxxxxxx.cn-beijing.maas.aliyuncs.com"
```

```bash
# bash / zsh
export DASHSCOPE_API_KEY="sk-xxxx"
export QWEN_IMAGE_BASE_URL="https://ws-xxxxxxxx.cn-beijing.maas.aliyuncs.com"
```

> **Key、接入点、模型必须属于同一地域/业务空间**，跨区调用会直接失败。
> 如果你和 JLwriter 桌面应用在同一台机器上，可直接加 `--use-jlwriter-key`，
> 插件会读取 `~/.story_editor_ai_config.json` 里的 Qwen Key 及其业务空间域名。

## 3. 命令行

```bash
# 一张首页主视觉
python -m qwen_image generate "SaaS 产品首页主视觉，抽象 3D 渐变" \
  --preset hero --style 3d --out public/images

# 空状态插画，输出 webp
python -m qwen_image generate "没有消息的空状态插画，打开的纸箱" \
  --preset empty_state --style line --ext webp

# 只看看会发什么请求（不需要 Key，不花钱）
python -m qwen_image generate "登录页背景" --preset hero --dry-run

# 批量出图（清单见 examples/assets.example.json）
python -m qwen_image batch qwen_image/examples/assets.example.json --jobs 3

# 查看所有预设与风格
python -m qwen_image presets
```

常用参数：

| 参数 | 作用 |
| --- | --- |
| `--preset hero` | 尺寸 + 构图提示一次性套用 |
| `--size 1600x900` | 自定义尺寸（优先于 `--preset`），需满足 512²~2048² 总面积、≤8:1 |
| `--style flat` | 风格词，见 `presets` 命令 |
| `--n 3` | 一次生成多张（1~6），文件名自动加序号 |
| `--seed 42` | 固定种子，方便复现与 A/B |
| `--image URL` | 参考图（图生图 / 局部改图），可重复 |
| `--allow-text` | 允许画面出现文字（默认反向词里排除文字） |
| `--ext webp` | 输出格式，jpg/webp 需要 Pillow |
| `--protocol async` | 改走异步任务 + 轮询，适合大批量 |
| `--json` | 机器可读输出，便于接 CI / 前端脚本 |

每次成功都会得到：

```
public/images/home-hero-hero-3f2a91c0.png          # 图片
public/images/home-hero-hero-3f2a91c0.png.json     # 同参数、seed、用量、源 URL
public/images/manifest.json                        # 仅 batch：整批索引
```

## 4. 内置预设

| 名称 | 尺寸 | 典型用途 |
| --- | --- | --- |
| `hero` | 1920×1080 | 首页首屏横幅，左侧留白放标题 |
| `hero_wide` | 2048×864 | 顶部通栏 / 超宽 Banner |
| `og` | 1200×630 | Open Graph 分享卡片 |
| `card` | 1200×900 | 卡片 / 博客封面 |
| `square` | 1024×1024 | 头像 / 商品方图 |
| `portrait` | 1152×1536 | 竖版卡片 / 详情页 |
| `mobile` | 1080×1920 | 移动端开屏 / 故事页 |
| `banner` | 2048×640 | 长条运营位 |
| `thumb` | 800×450 | 列表缩略图 |
| `empty_state` | 1024×768 | 空状态插画 |

风格：`photo` `flat` `3d` `minimal` `line` `isometric` `glass` `anime` `watercolor` `cyberpunk`，
也可以直接传自定义描述，例如 `--style "像素风，16bit 调色板"`。

示例输出（`qwen-image-3.0`，`thumb` 预设，800×450，耗时约 10.4 秒）：

![示例：极简登录页背景](examples/sample-thumb.png)

## 5. 批量清单

```json
{
  "out": "public/images",
  "style": "3d",
  "items": [
    { "name": "home-hero", "preset": "hero", "prompt": "漂浮的数据面板与光带" },
    { "name": "empty-inbox", "preset": "empty_state", "style": "line", "prompt": "空的收件箱插画" }
  ]
}
```

顶层支持 `out` / `style` / `preset` / `ext` / `negative_prompt` / `n` / `seed` / `allow_text`，
每一项都可以覆盖。批量结束后写 `out/manifest.json`，字段含 `name`、`files`、`prompt`、`error`。

## 6. Python API

```python
from qwen_image import QwenImageClient

client = QwenImageClient(protocol="openai")     # 或 protocol="async"
images = client.generate_to_dir(
    "空状态插画：没有消息",
    "public/images",
    preset="empty_state",
    style="flat",
    n=2,
    seed=20261026,
)
for image in images:
    print(image.local_path, image.size, image.seed, image.request_id)
```

只要 URL、不想落盘：

```python
images = client.generate("登录页背景", preset="hero")
print(images[0].url)          # 有效期 24 小时，记得尽快下载
```

图生图：

```python
images = client.generate(
    "把这张图改成夜间霓虹风格，保留构图",
    images=["https://example.com/ref.png"],
    size="1024x1024",
)
```

请求预览（不联网）：

```python
from qwen_image import build_request

request = build_request("登录页背景", preset="hero")
print(client.describe_request(request)["body"])
```

## 7. 前端接入

Vite / Vue / React 把 `public/` 当静态目录，直接引用即可：

```html
<img src="/images/home-hero-hero-3f2a91c0.png" alt="产品主视觉" />
```

```tsx
// React + Vite
import manifest from "../public/images/manifest.json";
const hero = manifest.items.find((item) => item.name === "home-hero");
```

```html
<!-- Open Graph -->
<meta property="og:image" content="https://example.com/images/home-og-og-1a2b3c4d.png" />
```

建议：

* `hero` / `banner` 用 `webp`，体积通常只有 PNG 的 1/4；
* 图标、头像裁成方形时直接用 `square`，避免二次裁切破坏构图；
* 生成后把 `.json` 元数据里的 `prompt` 一起提交，方便以后复现同一套视觉；
* 前端只依赖 `manifest.json` 与文件路径，替换模型不会影响页面。

## 8. 提示词小抄（前端素材）

* **说清用途**：“网页首屏横幅”“空状态插画”“应用图标”，模型会更懂构图。
* **指定留白方向**：`--preset` 已内置“左侧留白”“上下安全区”等提示，别再用 `--no-hint` 关掉。
* **默认无文字**：反向词已排除文字/水印；确实要文字时加 `--allow-text`，并在描述里写清内容。
* **一致性**：固定 `--style` 与 `--seed`，同一套页面的插画风格更容易统一。
* **复杂文字**：Qwen-Image-3.0 渲染文字较强，但仍建议在 UI 层叠加文本，避免生图出现错字。

## 9. 排查

| 现象 | 处理 |
| --- | --- |
| `缺少 API Key` | 设置 `DASHSCOPE_API_KEY`，或 `--api-key`，或 `--use-jlwriter-key` |
| `鉴权失败 (401)` | Key 与 `base_url` 不是同一地域/业务空间；检查是否用了国际站 Key 调北京域名 |
| `请求不被接受 (400)` | 看错误里的 `code`；常见是尺寸超限、`agent` 模式配参考图、`enable_thinking` 未开 `prompt_extend` |
| `触发限流 (429)` | 降低 `--jobs`，或稍后重试（客户端已带指数退避） |
| `等待任务超时` | 加 `--poll-timeout 600`，或改用 `--protocol openai` 同步调用 |
| 中文乱码 | 命令行已强制 UTF-8；Windows 旧终端建议用 Windows Terminal |
| 图片 URL 24 小时后失效 | 不要长期保存远端 URL，及时下载或使用插件的落盘能力 |

## 10. 说明

* 生成结果受平台内容安全策略约束，违规提示词会返回 400。
* 图片版权与商用授权请以百炼平台条款为准；上线前建议人工过一遍素材。
* `qwen-image-3.0-pro` 质量更高、耗时更长；`qwen-image-2.1-turbo` 更便宜，可通过 `--model` 切换。
  注意 2.1 系列不支持 `negative_prompt` / `prompt_extend_mode` / `enable_thinking`，
  插件会自动省掉这些字段（内置的默认反向词因此失效）。
* 本插件只依赖 `requests`，不修改 JLwriter 主程序，可独立复制到其它项目使用。
