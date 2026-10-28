"""命令行入口。

常用示例::

    python -m qwen_image generate "SaaS 产品首页主视觉，抽象 3D 渐变"
    python -m qwen_image generate "空状态插画：没有消息" --preset empty_state --style flat
    python -m qwen_image batch assets.json --jobs 3
    python -m qwen_image presets
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Dict, List, Optional

from .client import QwenImageClient, __version__, build_request
from .config import DEFAULT_PROTOCOL, resolve_model
from .errors import QwenImageError, QwenImageValidationError
from .presets import (
    STYLES,
    format_preset_table,
    list_presets,
)
from .storage import now_iso, relative_posix, write_json

DEFAULT_OUT_DIR = "assets/images"


# ------------------------------------------------------------------ 参数
def _add_common(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("接入配置")
    group.add_argument("--api-key", help="百炼 API Key（默认读 DASHSCOPE_API_KEY 等环境变量）")
    group.add_argument("--base-url", help="服务接入点，默认 https://dashscope.aliyuncs.com")
    group.add_argument("--workspace-id", help="业务空间 ID，用于 {workspace_id} 形式的域名")
    group.add_argument("--model", help="模型名，默认 qwen-image-3.0")
    group.add_argument(
        "--protocol",
        choices=("openai", "dashscope", "async"),
        default=DEFAULT_PROTOCOL,
        help="接入协议：openai（默认）/ dashscope 同步 / async 异步任务",
    )
    group.add_argument(
        "--use-jlwriter-key",
        action="store_true",
        help="复用 JLwriter 已保存的 Qwen Key 与其业务空间域名",
    )

    tuning = parser.add_argument_group("网络与调试")
    tuning.add_argument("--timeout", type=float, default=300.0, help="读取超时秒数，默认 300")
    tuning.add_argument("--retries", type=int, default=2, help="失败重试次数，默认 2")
    tuning.add_argument("--poll-interval", type=float, default=2.0, help="异步任务轮询间隔秒")
    tuning.add_argument("--poll-timeout", type=float, default=300.0, help="异步任务总超时秒")
    tuning.add_argument("--dry-run", action="store_true", help="只打印请求，不发送、不落盘")
    tuning.add_argument("--json", action="store_true", help="以 JSON 输出结果，便于脚本消费")
    tuning.add_argument("-v", "--verbose", action="store_true", help="打印接入点、Key 来源等调试信息")


def _add_render_args(parser: argparse.ArgumentParser) -> None:
    group = parser.add_argument_group("出图参数")
    group.add_argument("--preset", help="前端资源位预设，决定尺寸与构图提示（见 presets 命令）")
    group.add_argument("--size", help="自定义尺寸，如 1600x900（与 --preset 二选一，优先 --size）")
    group.add_argument("--style", help=f"风格：{' / '.join(STYLES)}，也可直接写描述")
    group.add_argument("--negative", dest="negative_prompt", help="自定义反向提示词")
    group.add_argument("--n", type=int, default=1, help="生成数量 1~6，默认 1")
    group.add_argument("--seed", type=int, help="随机种子，用于复现")
    group.add_argument("--image", action="append", default=[], help="参考图 URL / data URI，可重复")
    group.add_argument("--no-extend", action="store_true", help="关闭提示词智能改写")
    group.add_argument("--extend-mode", choices=("direct", "agent"), default="direct", help="改写模式")
    group.add_argument("--thinking", action="store_true", help="开启思考模式（更慢、质量更高）")
    group.add_argument("--watermark", action="store_true", help="添加水印")
    group.add_argument("--allow-text", action="store_true", help="允许画面出现文字（默认排斥文字）")
    group.add_argument("--no-hint", action="store_true", help="不追加预设的构图提示")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m qwen_image",
        description="调用 Qwen-Image-3.0 生成前端开发用的图片资源。",
        epilog=(
            "示例：\n"
            "  python -m qwen_image generate \"SaaS 首页主视觉\" --preset hero --style 3d\n"
            "  python -m qwen_image generate \"空状态插画\" --preset empty_state --ext webp\n"
            "  python -m qwen_image batch assets.json --jobs 3\n"
            "  python -m qwen_image presets"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=f"qwen_image {__version__}")
    subparsers = parser.add_subparsers(dest="command", metavar="命令")

    common = argparse.ArgumentParser(add_help=False)
    _add_common(common)

    generate = subparsers.add_parser(
        "generate", parents=[common], help="生成图片并下载到本地"
    )
    generate.add_argument("prompt", nargs="+", help="画面描述（中英文均可）")
    _add_render_args(generate)

    output = generate.add_argument_group("输出")
    output.add_argument("--out", default=DEFAULT_OUT_DIR, help=f"输出目录，默认 {DEFAULT_OUT_DIR}")
    output.add_argument("--name", help="文件名主干，默认由提示词生成")
    output.add_argument("--ext", choices=("png", "jpg", "webp"), default="png", help="输出格式")
    output.add_argument("--quality", type=int, default=88, help="jpg/webp 质量，默认 88")
    output.add_argument("--no-download", action="store_true", help="只返回远端 URL，不下载")

    batch = subparsers.add_parser(
        "batch", parents=[common], help="按 JSON 清单批量出图"
    )
    batch.add_argument("manifest", help="清单文件路径，见 qwen_image/examples/assets.example.json")
    batch.add_argument("--out", help="覆盖清单里的输出目录")
    batch.add_argument("--jobs", type=int, default=2, help="并发数，默认 2")
    batch.add_argument("--ext", choices=("png", "jpg", "webp"), help="覆盖清单里的输出格式")
    batch.add_argument("--quality", type=int, default=88, help="jpg/webp 质量")
    batch.add_argument("--allow-text", action="store_true", help="允许画面出现文字")

    presets = subparsers.add_parser("presets", help="列出预设尺寸与风格")
    presets.add_argument("--json", action="store_true", help="以 JSON 输出")

    return parser


# ------------------------------------------------------------------ 工具
def _mask_key(key: Optional[str]) -> str:
    if not key:
        return "(未配置)"
    if len(key) <= 8:
        return "*" * len(key)
    return f"{key[:4]}...{key[-4:]}"


def _client(args: argparse.Namespace) -> QwenImageClient:
    return QwenImageClient(
        api_key=args.api_key,
        base_url=args.base_url,
        workspace_id=args.workspace_id,
        model=args.model,
        protocol=args.protocol,
        timeout=args.timeout,
        max_retries=args.retries,
        poll_interval=args.poll_interval,
        poll_timeout=args.poll_timeout,
        use_jlwriter_key=args.use_jlwriter_key,
    )


def _render_kwargs(args: argparse.Namespace) -> Dict[str, Any]:
    return {
        "preset": args.preset,
        "style": args.style,
        "size": args.size,
        "negative_prompt": args.negative_prompt,
        "n": args.n,
        "seed": args.seed,
        "images": args.image or None,
        "prompt_extend": not args.no_extend,
        "prompt_extend_mode": args.extend_mode,
        "enable_thinking": args.thinking,
        "watermark": args.watermark,
        "allow_text": args.allow_text,
        "include_hint": not args.no_hint,
    }


def _print_json(payload: Dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _verbose_banner(client: QwenImageClient) -> None:
    print(
        f"接入点 {client.base_url}\n"
        f"模型   {client.model}    协议 {client.protocol}\n"
        f"Key    {_mask_key(client.api_key)}（来源：{client.credential_source}）",
        file=sys.stderr,
    )


# ------------------------------------------------------------------ generate
def _cmd_generate(args: argparse.Namespace) -> int:
    prompt = " ".join(args.prompt).strip()
    client = _client(args)
    kwargs = _render_kwargs(args)

    if args.dry_run:
        request = build_request(prompt, **kwargs)
        described = client.describe_request(request)
        payload = {
            "ok": True,
            "dry_run": True,
            "protocol": client.protocol,
            "model": client.model,
            "requests": [described],
        }
        if args.json:
            _print_json(payload)
        else:
            print(f"[dry-run] {described['protocol']} → {described['endpoint']}")
            print(json.dumps(described["body"], ensure_ascii=False, indent=2))
        return 0

    if args.verbose:
        _verbose_banner(client)

    started = time.monotonic()
    if args.no_download:
        images = client.generate(prompt, **kwargs)
        if not args.json:
            for index, image in enumerate(images, start=1):
                print(f"[{index}/{len(images)}] {image.url}  {image.size}")
    else:
        images = client.generate_to_dir(
            prompt,
            args.out,
            name=args.name,
            ext=args.ext,
            quality=args.quality,
            **kwargs,
        )
        if not args.json:
            for index, image in enumerate(images, start=1):
                print(
                    f"[{index}/{len(images)}] {image.local_path}  "
                    f"{image.size}  {image.elapsed_s}s"
                )
                if image.metadata_path:
                    print(f"        元数据 {image.metadata_path}")
    elapsed = round(time.monotonic() - started, 2)

    if args.json:
        _print_json(
            {
                "ok": True,
                "command": "generate",
                "elapsed_s": elapsed,
                "images": [image.to_dict() for image in images],
            }
        )
    return 0


# ------------------------------------------------------------------ batch
def _load_manifest(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except OSError as exc:
        raise QwenImageValidationError(f"读不到清单文件 {path}：{exc}") from exc
    except ValueError as exc:
        raise QwenImageValidationError(f"清单文件不是合法 JSON：{exc}") from exc

    if isinstance(data, list):
        data = {"items": data}
    if not isinstance(data, dict):
        raise QwenImageValidationError("清单文件顶层必须是对象或数组")
    items = data.get("items")
    if not isinstance(items, list) or not items:
        raise QwenImageValidationError("清单文件缺少非空的 items 数组")
    return data


def _normalize_batch_item(
    item: Dict[str, Any], manifest: Dict[str, Any], args: argparse.Namespace
) -> Dict[str, Any]:
    if not isinstance(item, dict):
        raise QwenImageValidationError("items 里每一项都必须是对象")
    prompt = str(item.get("prompt") or "").strip()
    if not prompt:
        raise QwenImageValidationError(f"清单项缺少 prompt：{item!r}")

    def pick(key: str, fallback: Any = None) -> Any:
        if key in item and item[key] is not None:
            return item[key]
        return manifest.get(key, fallback)

    images = item.get("images") or item.get("image") or None
    if isinstance(images, str):
        images = [images]
    return {
        "name": item.get("name"),
        "prompt": prompt,
        "preset": pick("preset"),
        "style": pick("style"),
        "size": pick("size"),
        "negative_prompt": pick("negative_prompt"),
        "n": int(item.get("n") or manifest.get("n") or 1),
        "seed": item.get("seed", manifest.get("seed")),
        "images": images,
        "allow_text": bool(pick("allow_text", getattr(args, "allow_text", False))),
        "ext": item.get("ext") or manifest.get("ext") or args.ext or "png",
        "quality": int(item.get("quality") or manifest.get("quality") or args.quality),
    }


def _batch_worker(
    args: argparse.Namespace,
    spec: Dict[str, Any],
    out_dir: str,
) -> Dict[str, Any]:
    client = _client(args)
    try:
        images = client.generate_to_dir(
            spec["prompt"],
            out_dir,
            name=spec["name"],
            ext=spec["ext"],
            quality=spec["quality"],
            preset=spec["preset"],
            style=spec["style"],
            size=spec["size"],
            negative_prompt=spec["negative_prompt"],
            n=spec["n"],
            seed=spec["seed"],
            images=spec["images"],
            allow_text=spec["allow_text"],
        )
        return {
            "name": spec["name"] or spec["prompt"][:24],
            "prompt": spec["prompt"],
            "files": [image.local_path for image in images],
            "images": [image.to_dict() for image in images],
        }
    finally:
        client.close()


def _cmd_batch(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = _load_manifest(manifest_path)
    out_dir = args.out or manifest.get("out") or DEFAULT_OUT_DIR
    specs = [_normalize_batch_item(item, manifest, args) for item in manifest["items"]]

    if args.dry_run:
        client = _client(args)
        requests_payload = []
        for spec in specs:
            request = build_request(
                spec["prompt"],
                preset=spec["preset"],
                style=spec["style"],
                size=spec["size"],
                negative_prompt=spec["negative_prompt"],
                n=spec["n"],
                seed=spec["seed"],
                images=spec["images"],
                allow_text=spec["allow_text"],
            )
            described = client.describe_request(request)
            described["name"] = spec["name"]
            requests_payload.append(described)
        payload = {
            "ok": True,
            "dry_run": True,
            "protocol": client.protocol,
            "model": client.model,
            "out": out_dir,
            "requests": requests_payload,
        }
        client.close()
        if args.json:
            _print_json(payload)
        else:
            for described in requests_payload:
                print(f"[dry-run] {described['name'] or '-'} → {described['endpoint']}")
                print(json.dumps(described["body"], ensure_ascii=False, indent=2))
        return 0

    started = time.monotonic()
    results: List[Optional[Dict[str, Any]]] = [None] * len(specs)
    failures = 0

    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {
            pool.submit(_batch_worker, args, spec, out_dir): index
            for index, spec in enumerate(specs)
        }
        for future in as_completed(futures):
            index = futures[future]
            spec = specs[index]
            try:
                result = future.result()
                results[index] = result
                if not args.json:
                    print(
                        f"[{index + 1}/{len(specs)}] {result['name']}: "
                        f"{len(result['files'])} 张 → {out_dir}"
                    )
            except Exception as exc:  # 单个素材失败不应中断整批
                failures += 1
                results[index] = {
                    "name": spec["name"] or spec["prompt"][:24],
                    "prompt": spec["prompt"],
                    "files": [],
                    "error": str(exc),
                }
                if not args.json:
                    print(
                        f"[{index + 1}/{len(specs)}] 失败：{spec['name'] or spec['prompt'][:24]}"
                        f" — {exc}",
                        file=sys.stderr,
                    )

    elapsed = round(time.monotonic() - started, 2)
    manifest_out = Path(out_dir) / "manifest.json"
    entries = []
    for result in results:
        if result is None:
            continue
        entry = {key: value for key, value in result.items() if key != "images"}
        entry["files"] = [relative_posix(Path(path), Path(out_dir)) for path in result["files"]]
        entries.append(entry)
    write_json(
        manifest_out,
        {
            "generated_at": now_iso(),
            "model": resolve_model(args.model),
            "out": str(out_dir),
            "items": entries,
        },
    )

    if args.json:
        _print_json(
            {
                "ok": failures == 0,
                "command": "batch",
                "elapsed_s": elapsed,
                "out": str(out_dir),
                "manifest": str(manifest_out),
                "items": entries,
            }
        )
    else:
        print(f"清单已写入 {manifest_out}")
    return 0 if failures == 0 else 1


# ------------------------------------------------------------------ presets
def _cmd_presets(args: argparse.Namespace) -> int:
    if args.json:
        _print_json(
            {
                "presets": [
                    {
                        "name": preset.name,
                        "width": preset.width,
                        "height": preset.height,
                        "aspect": preset.aspect,
                        "label": preset.label,
                    }
                    for preset in list_presets()
                ],
                "styles": STYLES,
            }
        )
        return 0
    print("尺寸预设（Qwen-Image-3.0 输出）\n")
    print(format_preset_table())
    print("\n风格（--style）\n")
    for name, description in STYLES.items():
        print(f"  {name:<12} {description}")
    print("\n用法：python -m qwen_image generate \"画面描述\" --preset hero --style 3d")
    return 0


# ------------------------------------------------------------------ 入口
def main(argv: Optional[List[str]] = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:  # Windows 控制台默认 GBK，固定 UTF-8 避免中文乱码/报错
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2

    try:
        if args.command == "generate":
            return _cmd_generate(args)
        if args.command == "batch":
            return _cmd_batch(args)
        if args.command == "presets":
            return _cmd_presets(args)
    except QwenImageError as exc:
        if getattr(args, "json", False):
            _print_json(
                {
                    "ok": False,
                    "error": {
                        "type": type(exc).__name__,
                        "message": exc.message,
                        "code": exc.code,
                        "status_code": exc.status_code,
                        "request_id": exc.request_id,
                    },
                }
            )
        else:
            print(f"失败：{exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("已中断", file=sys.stderr)
        return 130

    parser.print_help()
    return 2
