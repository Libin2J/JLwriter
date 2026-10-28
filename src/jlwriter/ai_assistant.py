"""
LLM 请求线程：OpenAI SDK + 流式响应 + 截断检测
"""
import json
from PyQt5.QtCore import QThread, pyqtSignal

try:
    import openai
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import json_repair  # noqa: F401 - 仅用于探测依赖是否可用
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False

try:
    from .prompt_history import PromptHistory
    HAS_PROMPT_HISTORY = True
except ImportError:
    HAS_PROMPT_HISTORY = False


DEFAULT_MAX_TOKENS = 8192*8


class AIRequestThread(QThread):
    finished = pyqtSignal(str)
    error = pyqtSignal(str)
    chunk = pyqtSignal(str)

    def __init__(self, resolved_agent, prompt, parent=None,
                 max_tokens=DEFAULT_MAX_TOKENS,
                 json_mode=False,
                 timeout=60):
        super().__init__(parent)
        # 防御：明确要求 ResolvedAgent
        if not hasattr(resolved_agent, "base_url"):
            raise TypeError(
                f"AIRequestThread 需要 ResolvedAgent，收到的是 "
                f"{type(resolved_agent).__name__}。请使用 "
                f"ai_config.resolve_agent('xxx') 获取配置。"
            )
        self.agent = resolved_agent
        self.prompt = prompt
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self.timeout = timeout
        self._stop_requested = False  # 新增
        self._stream_handle = None  # 新增：保存流式响应句柄

    def _build_messages(self):
        system_parts = []

        if self.agent.persona:
            system_parts.append(self.agent.persona)

        style = getattr(self.agent, "style", "")
        if style:
            system_parts.append(
                f"【写作风格要求】{style}\n"
                f"请在输出中严格体现上述风格特征，包括用词、句式、节奏、语气。\n"
                f"风格不是装饰，而是输出的一部分：每句话、每个对话、每段描写"
                f"都应体现该风格。"
            )

        system_content = "\n\n".join(system_parts) or "你是一个专业的写作助手"
        user_content = self.prompt

        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content},
        ]

    def run(self):
        try:
            if self._stop_requested:
                return
            if not self.agent:
                self.error.emit("Agent 配置未解析，无法调用 API")
                return

            # 记录本次 prompt，供审查与优化
            if HAS_PROMPT_HISTORY:
                try:
                    messages = self._build_messages()
                    system_content = messages[0]["content"] if messages else ""
                    user_content = (
                        messages[1]["content"] if len(messages) > 1 else ""
                    )
                    full_prompt = (
                        f"=== SYSTEM ===\n{system_content}\n\n"
                        f"=== USER ===\n{user_content}"
                    )
                    PromptHistory.instance().add(
                        agent_name=getattr(self.agent, "name", "unknown"),
                        provider=getattr(self.agent, "provider", ""),
                        model=getattr(self.agent, "model", ""),
                        prompt=full_prompt,
                    )
                except Exception:
                    pass

            if not self.agent.api_key:
                self.error.emit(
                    f"未配置 {self.agent.provider} 的 API Key，"
                    f"请在设置中填写"
                )
                return
            if HAS_OPENAI:
                self._run_with_openai_sdk()
            elif HAS_REQUESTS:
                self._run_with_requests()
            else:
                self.error.emit("未安装 openai 或 requests，无法调用 API")
        except Exception as e:
            if self._stop_requested:
                return
            import traceback
            traceback.print_exc()
            self.error.emit(f"{type(e).__name__}: {e}")

    def _run_with_openai_sdk(self):
        client_kwargs = {
            "api_key": self.agent.api_key,
            "timeout": self.timeout,
            "max_retries": 0,
        }
        if self.agent.base_url:
            client_kwargs["base_url"] = self.agent.base_url
        client = openai.OpenAI(**client_kwargs)

        create_kwargs = dict(
            model=self.agent.model,
            messages=self._build_messages(),
            temperature=0.8,
            max_tokens=self.max_tokens,
            stream=True,
        )
        if self.json_mode and self.agent.provider in ("openai", "gemini"):
            create_kwargs["response_format"] = {"type": "json_object"}

        full_content = ""
        finish_reason = None

        try:
            stream = client.chat.completions.create(**create_kwargs)
            self._stream_handle = stream  # 保存句柄
            for chunk in stream:
                # 每次迭代检查中断
                if self._stop_requested:
                    try:
                        stream.close()
                    except Exception:
                        pass
                    self._stream_handle = None
                    return  # 直接返回，不发信号

                if not chunk.choices:
                    continue
                choice = chunk.choices[0]
                delta = getattr(choice, "delta", None)
                if delta is not None:
                    content = getattr(delta, "content", None)
                    if content:
                        full_content += content
                        self.chunk.emit(content)
                fr = getattr(choice, "finish_reason", None)
                if fr:
                    finish_reason = fr
        except openai.LengthFinishReasonError:
            if self._stop_requested:
                self._stream_handle = None
                return
            self.error.emit(
                f"输出被截断（达到 max_tokens={self.max_tokens}），"
                "请调大 max_tokens 或让模型分次输出"
            )
            return
        except Exception as e:
            if self._stop_requested:
                self._stream_handle = None
                return
            raise
        finally:
            self._stream_handle = None

        if self._stop_requested:
            return
        self._emit_result(full_content, finish_reason)

    def _run_with_requests(self):
        base_url = self.agent.base_url
        if base_url:
            url = base_url.rstrip("/") + "/chat/completions"
        else:
            url = "https://api.openai.com/v1/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.agent.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.agent.model,
            "messages": self._build_messages(),
            "temperature": 0.8,
            "max_tokens": self.max_tokens,
            "stream": True,
        }

        full_content = ""
        finish_reason = None

        with requests.post(
                url, json=payload, headers=headers,
                stream=True, timeout=(10, self.timeout + 30)
        ) as resp:
            self._stream_handle = resp
            resp.raise_for_status()
            for raw_line in resp.iter_lines():
                if self._stop_requested:
                    self._stream_handle = None
                    return
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode("utf-8")
                except Exception:
                    continue
                if not line.startswith("data: "):
                    continue
                data_str = line[6:].strip()
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                choices = data.get("choices") or []
                if not choices:
                    continue
                delta = choices[0].get("delta") or {}
                content = delta.get("content")
                if content:
                    full_content += content
                    self.chunk.emit(content)
                fr = choices[0].get("finish_reason")
                if fr:
                    finish_reason = fr

        self._stream_handle = None
        if self._stop_requested:
            return
        self._emit_result(full_content, finish_reason)

    def _emit_result(self, full_content, finish_reason):
        if finish_reason == "length":
            self.finished.emit(full_content)
            self.error.emit(
                f"提示：输出因 max_tokens={self.max_tokens} 被截断，"
                "结果可能不完整"
            )
            return
        self.finished.emit(full_content)

    def stop(self):
        """请求停止线程：设置标志，流式循环下次迭代即退出"""
        self._stop_requested = True
        # 若已拿到流句柄，尝试主动关闭以加快退出
        try:
            if self._stream_handle is not None:
                self._stream_handle.close()
        except Exception:
            pass