"""qwen_image 的离线测试：用本地伪服务器跑通三种协议，不访问外网、不消耗额度。"""
from __future__ import annotations

import base64
import io
import itertools
import json
import os
import shutil
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from qwen_image import (
    PRESETS,
    QwenImageAuthError,
    QwenImageClient,
    QwenImageTaskFailed,
    QwenImageValidationError,
    build_request,
    validate_size,
)
from qwen_image.cli import main
from qwen_image.config import load_jlwriter_credentials

PNG_1PX = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

# 沙箱只允许写工作区，临时目录也放在 tests/_tmp 下。
# 注意：不要用 tempfile.mkdtemp —— 它以 0o700 建目录，在 Windows 沙箱里会得到
# 一个当前用户都进不去的目录，改用普通 mkdir 并自己保证名字唯一。
BASE_TMP = Path(__file__).resolve().parent / "_tmp"
_SEQUENCE = itertools.count()


def make_temp_dir() -> Path:
    BASE_TMP.mkdir(parents=True, exist_ok=True)
    while True:
        candidate = BASE_TMP / f"run_{os.getpid()}_{next(_SEQUENCE)}"
        try:
            candidate.mkdir()
            return candidate
        except FileExistsError:
            continue


class FakeQwenServer:
    """模拟百炼的三类生图接口和一个图片下载地址。"""

    def __init__(self) -> None:
        self.requests: list = []
        self.poll_count = 0
        self.fail_times = 0
        self.auth_fail = False
        self.pending_rounds = 2
        self.final_status = "SUCCEEDED"
        self.use_b64 = False
        self.width = 1920
        self.height = 1080

        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # 静默
                pass

            def _send_json(self, payload, status=200):
                data = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("x-request-id", "req-http")
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length)
                try:
                    body = json.loads(raw.decode("utf-8"))
                except Exception:
                    body = {}
                outer.requests.append(
                    {
                        "path": self.path,
                        "body": body,
                        "headers": {key.lower(): value for key, value in self.headers.items()},
                    }
                )

                if outer.fail_times > 0:
                    outer.fail_times -= 1
                    self._send_json({"error": {"message": "temporary failure"}}, 500)
                    return
                if outer.auth_fail:
                    self._send_json(
                        {"error": {"message": "Invalid API-key", "code": "InvalidApiKey"}},
                        401,
                    )
                    return

                if self.path.endswith("/compatible-mode/v1/images/generations"):
                    size = str(body.get("size") or "1024x1024")
                    width, height = [int(part) for part in size.replace("*", "x").split("x")]
                    outer.width, outer.height = width, height
                    if outer.use_b64:
                        item = {"b64_json": base64.b64encode(PNG_1PX).decode("ascii")}
                    else:
                        item = {"url": f"{outer.base_url}/files/out.png"}
                    self._send_json(
                        {
                            "created": 1,
                            "data": [item],
                            "usage": {
                                "output_width": width,
                                "output_height": height,
                                "output_image_count": 1,
                                "input_image_count": 0,
                            },
                        }
                    )
                    return

                if self.path.endswith("/multimodal-generation/generation"):
                    self._send_json(
                        {
                            "output": {
                                "choices": [
                                    {
                                        "finish_reason": "stop",
                                        "message": {
                                            "role": "assistant",
                                            "content": [
                                                {"image": f"{outer.base_url}/files/out.png"}
                                            ],
                                        },
                                    }
                                ]
                            },
                            "usage": {"width": 1200, "height": 900, "image_count": 1},
                            "request_id": "req-dashscope",
                        }
                    )
                    return

                if self.path.endswith("/aigc/image-generation/generation"):
                    self._send_json(
                        {
                            "output": {"task_id": "task-1", "task_status": "PENDING"},
                            "request_id": "req-async",
                        }
                    )
                    return

                self._send_json({"error": {"message": "not found"}}, 404)

            def do_GET(self):
                if self.path.startswith("/api/v1/tasks/"):
                    outer.poll_count += 1
                    if outer.poll_count <= outer.pending_rounds:
                        self._send_json(
                            {
                                "output": {"task_id": "task-1", "task_status": "PENDING"},
                                "request_id": "req-poll",
                            }
                        )
                        return
                    if outer.final_status != "SUCCEEDED":
                        self._send_json(
                            {
                                "output": {
                                    "task_id": "task-1",
                                    "task_status": outer.final_status,
                                    "code": "InternalError",
                                    "message": "boom",
                                },
                                "request_id": "req-failed",
                            }
                        )
                        return
                    self._send_json(
                        {
                            "output": {
                                "task_id": "task-1",
                                "task_status": "SUCCEEDED",
                                "choices": [
                                    {
                                        "finish_reason": "stop",
                                        "message": {
                                            "role": "assistant",
                                            "content": [
                                                {"image": f"{outer.base_url}/files/out.png"}
                                            ],
                                        },
                                    }
                                ],
                            },
                            "usage": {"output_width": 1080, "output_height": 1920},
                            "request_id": "req-done",
                        }
                    )
                    return
                if self.path == "/files/out.png":
                    self.send_response(200)
                    self.send_header("Content-Type", "image/png")
                    self.send_header("Content-Length", str(len(PNG_1PX)))
                    self.end_headers()
                    self.wfile.write(PNG_1PX)
                    return
                self._send_json({"error": {"message": "not found"}}, 404)

        self._httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()
        self.base_url = f"http://127.0.0.1:{self._httpd.server_address[1]}"

    def close(self) -> None:
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=2)


class ClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.server = FakeQwenServer()
        self.tmp = make_temp_dir()
        self.out = self.tmp / "public" / "images"

    def tearDown(self) -> None:
        self.server.close()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _client(self, **overrides) -> QwenImageClient:
        kwargs = dict(
            api_key="sk-test",
            base_url=self.server.base_url,
            model="qwen-image-3.0",
            timeout=(2.0, 5.0),
            max_retries=0,
            poll_interval=0.01,
            poll_timeout=5.0,
        )
        kwargs.update(overrides)
        client = QwenImageClient(**kwargs)
        client._sleep = lambda _seconds: None  # 测试里不真的等待
        client._random = lambda: 0.0
        return client

    # ---------------------------------------------------------- openai
    def test_openai_generate_downloads_and_writes_metadata(self):
        client = self._client()
        images = client.generate_to_dir(
            "SaaS 产品首页主视觉", str(self.out), preset="hero", style="3d"
        )

        self.assertEqual(len(images), 1)
        image = images[0]
        path = Path(image.local_path)
        self.assertTrue(path.exists())
        self.assertEqual(path.suffix, ".png")
        self.assertTrue(path.read_bytes().startswith(b"\x89PNG"))
        self.assertTrue(Path(image.metadata_path).exists())

        metadata = json.loads(Path(image.metadata_path).read_text(encoding="utf-8"))
        self.assertEqual(metadata["preset"], "hero")
        self.assertEqual(metadata["size"], "1920x1080")
        self.assertEqual(metadata["negative_prompt"].count("文字"), 2)  # “文字”与“UI 文字”
        self.assertEqual(metadata["width"], 1920)
        self.assertEqual(metadata["request_id"], "req-http")

        sent = self.server.requests[0]
        self.assertTrue(sent["path"].endswith("/compatible-mode/v1/images/generations"))
        self.assertEqual(sent["body"]["model"], "qwen-image-3.0")
        self.assertEqual(sent["body"]["size"], "1920x1080")
        self.assertIn("3D 渲染", sent["body"]["prompt"])
        self.assertIn("左侧留出", sent["body"]["prompt"])
        self.assertEqual(sent["headers"]["authorization"], "Bearer sk-test")

    def test_openai_base64_result_is_saved(self):
        self.server.use_b64 = True
        client = self._client()
        images = client.generate_to_dir("品牌图标", str(self.out), preset="square")
        self.assertTrue(Path(images[0].local_path).read_bytes().startswith(b"\x89PNG"))

    # ---------------------------------------------------------- dashscope
    def test_dashscope_sync_payload_shape(self):
        client = self._client(protocol="dashscope")
        images = client.generate("卡片封面", preset="card", seed=7)

        self.assertEqual(len(images), 1)
        self.assertEqual(images[0].width, 1200)
        self.assertEqual(images[0].seed, 7)

        body = self.server.requests[0]["body"]
        self.assertEqual(body["model"], "qwen-image-3.0")
        self.assertEqual(body["parameters"]["size"], "1200*900")
        self.assertEqual(body["parameters"]["seed"], 7)
        content = body["input"]["messages"][0]["content"]
        self.assertTrue(content[-1]["text"].startswith("卡片封面"))
        self.assertIn("主体居中", content[-1]["text"])  # 预设里的构图提示

    # ---------------------------------------------------------- async
    def test_async_submits_and_polls_until_success(self):
        client = self._client(protocol="async")
        images = client.generate_to_dir("移动端开屏", str(self.out), preset="mobile")

        self.assertGreaterEqual(self.server.poll_count, 3)
        self.assertEqual(images[0].task_id, "task-1")
        self.assertEqual(images[0].width, 1080)
        self.assertEqual(images[0].height, 1920)
        self.assertTrue(Path(images[0].local_path).exists())

        submit = self.server.requests[0]
        self.assertTrue(submit["path"].endswith("/aigc/image-generation/generation"))
        self.assertEqual(submit["headers"].get("x-dashscope-async"), "enable")

    def test_async_failed_task_raises(self):
        self.server.pending_rounds = 0
        self.server.final_status = "FAILED"

        client = self._client(protocol="async")
        with self.assertRaises(QwenImageTaskFailed) as context:
            client.generate("失败任务")
        self.assertEqual(context.exception.code, "InternalError")

    # ---------------------------------------------------------- 错误与重试
    def test_auth_error_maps_to_specific_exception(self):
        self.server.auth_fail = True
        client = self._client()
        with self.assertRaises(QwenImageAuthError) as context:
            client.generate("测试")
        self.assertEqual(context.exception.status_code, 401)
        self.assertEqual(context.exception.code, "InvalidApiKey")

    def test_retries_on_500_then_succeeds(self):
        self.server.fail_times = 1
        client = self._client(max_retries=1)
        images = client.generate("重试成功")
        self.assertEqual(len(images), 1)
        self.assertEqual(len(self.server.requests), 2)

    def test_missing_api_key_raises_config_error(self):
        from unittest import mock

        from qwen_image import QwenImageConfigError

        with mock.patch.dict(
            "os.environ",
            {
                "DASHSCOPE_API_KEY": "",
                "QWEN_IMAGE_API_KEY": "",
                "QWEN_API_KEY": "",
            },
        ):
            client = QwenImageClient(api_key="", base_url=self.server.base_url)
            with self.assertRaises(QwenImageConfigError):
                client.generate("没有 Key")


class ValidationTests(unittest.TestCase):
    def test_presets_are_within_api_limits(self):
        for preset in PRESETS.values():
            width, height = validate_size(preset.width, preset.height)
            self.assertEqual((width, height), preset.size)

    def test_rejects_bad_sizes(self):
        for size in ("100x100", "3000x3000", "1600x100", "abc"):
            with self.assertRaises(QwenImageValidationError):
                build_request("测试", size=size)

    def test_rejects_empty_prompt_and_bad_options(self):
        with self.assertRaises(QwenImageValidationError):
            build_request("   ")
        with self.assertRaises(QwenImageValidationError):
            build_request("测试", n=9)
        with self.assertRaises(QwenImageValidationError):
            build_request("测试", enable_thinking=True, prompt_extend=False)
        with self.assertRaises(QwenImageValidationError):
            build_request("测试", images=["https://x/y.png"], prompt_extend_mode="agent")

    def test_prompt_composition_and_negative_defaults(self):
        request = build_request("登录页背景", preset="hero", style="minimal")
        self.assertIn("登录页背景", request.prompt)
        self.assertIn("极简主义", request.prompt)
        self.assertIn("左侧留出", request.prompt)
        self.assertEqual(request.preset_name, "hero")
        self.assertIn("文字", request.negative_prompt)
        self.assertNotIn("文字", build_request("登录页背景", allow_text=True).negative_prompt)

    def test_custom_negative_prompt_wins(self):
        request = build_request("测试", negative_prompt="只保留这句话")
        self.assertEqual(request.negative_prompt, "只保留这句话")

    def test_qwen_21_payload_omits_unsupported_fields(self):
        request = build_request("测试", preset="card")
        body = request.to_openai_payload("qwen-image-2.1-turbo")
        self.assertNotIn("negative_prompt", body)
        self.assertNotIn("enable_thinking", body)
        self.assertNotIn("prompt_extend_mode", body)
        self.assertEqual(body["prompt_extend"], True)

    def test_chinese_prompt_does_not_repeat_hash_in_filename(self):
        from qwen_image.storage import build_stem, short_hash

        digest = short_hash("纯中文提示词")
        self.assertEqual(build_stem("纯中文提示词", "hero"), f"img-{digest}-hero")
        self.assertEqual(
            build_stem("hero banner", "hero", 42), "hero-banner-hero-42"
        )


class CliTests(unittest.TestCase):
    def _run(self, argv):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            code = main(argv)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_dry_run_prints_request_without_key(self):
        code, stdout, _ = self._run(
            ["generate", "登录页背景", "--preset", "hero", "--dry-run", "--json"]
        )
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertTrue(payload["dry_run"])
        self.assertEqual(payload["requests"][0]["body"]["size"], "1920x1080")
        self.assertEqual(payload["requests"][0]["protocol"], "openai")

    def test_batch_dry_run_reads_manifest(self):
        tmp = make_temp_dir()
        try:
            manifest = tmp / "assets.json"
            manifest.write_text(
                json.dumps(
                    {
                        "out": "public/images",
                        "style": "flat",
                        "items": [
                            {"name": "a", "preset": "og", "prompt": "分享卡片"},
                            {"name": "b", "preset": "square", "prompt": "头像"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            code, stdout, _ = self._run(["batch", str(manifest), "--dry-run", "--json"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        self.assertEqual(len(payload["requests"]), 2)
        self.assertEqual(payload["requests"][0]["body"]["size"], "1200x630")
        self.assertEqual(payload["out"], "public/images")

    def test_presets_command_outputs_json(self):
        code, stdout, _ = self._run(["presets", "--json"])
        self.assertEqual(code, 0)
        payload = json.loads(stdout)
        names = {item["name"] for item in payload["presets"]}
        self.assertIn("hero", names)
        self.assertIn("3d", payload["styles"])

    def test_generate_json_output_is_pure_json(self):
        server = FakeQwenServer()
        tmp = make_temp_dir()
        try:
            code, stdout, _ = self._run(
                [
                    "generate",
                    "空状态插画：没有消息",
                    "--preset",
                    "thumb",
                    "--api-key",
                    "sk-test",
                    "--base-url",
                    server.base_url,
                    "--out",
                    str(tmp / "images"),
                    "--json",
                ]
            )
            payload = json.loads(stdout)  # 不能混入人类可读的进度行
            saved = Path(payload["images"][0]["local_path"]).exists()
        finally:
            server.close()
            shutil.rmtree(tmp, ignore_errors=True)

        self.assertEqual(code, 0)
        self.assertTrue(payload["ok"])
        self.assertTrue(saved)

    def test_unknown_preset_fails_with_message(self):
        code, _, stderr = self._run(["generate", "测试", "--preset", "nope", "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("未知预设", stderr)


class ConfigTests(unittest.TestCase):
    def test_reads_jlwriter_encrypted_key(self):
        key = "sk-jlwriter-test"
        secret = b"StoryEditor2024!AI"
        stream = key.encode("utf-8")
        masked = bytes(
            byte ^ secret[index % len(secret)] for index, byte in enumerate(stream)
        )
        token = base64.b64encode(masked).decode("ascii")

        tmp = make_temp_dir()
        try:
            path = tmp / "config.json"
            path.write_text(
                json.dumps({"api_keys": {"qwen": token}}), encoding="utf-8"
            )
            loaded_key, _ = load_jlwriter_credentials(path)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        self.assertEqual(loaded_key, key)


if __name__ == "__main__":
    unittest.main()
