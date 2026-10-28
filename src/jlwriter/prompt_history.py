"""
全局 Prompt 历史记录：记录最近发送给 LLM 的 prompt，供审查与优化
"""
import time
from dataclasses import dataclass, field
from typing import List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


MAX_HISTORY = 50


@dataclass
class PromptRecord:
    timestamp: float
    agent_name: str
    provider: str
    model: str
    prompt: str
    extra: dict = field(default_factory=dict)

    @property
    def time_str(self):
        return time.strftime("%Y-%m-%d %H:%M:%S",
                             time.localtime(self.timestamp))

    @property
    def short_time(self):
        return time.strftime("%H:%M:%S", time.localtime(self.timestamp))

    def summary(self, max_len=40):
        text = (self.prompt or "").replace("\n", " ").strip()
        if len(text) > max_len:
            text = text[:max_len] + "…"
        return text or "（空）"


class PromptHistory(QObject):
    """单例式历史记录；任何位置调用 instance() 获取同一实例"""
    updated = pyqtSignal()

    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        super().__init__()
        self._records: List[PromptRecord] = []

    def add(self, agent_name, provider, model, prompt, extra=None):
        record = PromptRecord(
            timestamp=time.time(),
            agent_name=agent_name or "unknown",
            provider=provider or "",
            model=model or "",
            prompt=prompt or "",
            extra=extra or {},
        )
        self._records.insert(0, record)
        if len(self._records) > MAX_HISTORY:
            self._records = self._records[:MAX_HISTORY]
        # 跨线程自动排队到主线程
        self.updated.emit()

    def all_records(self) -> List[PromptRecord]:
        return list(self._records)

    def latest(self) -> Optional[PromptRecord]:
        return self._records[0] if self._records else None

    def agent_names(self) -> List[str]:
        seen = []
        for r in self._records:
            if r.agent_name not in seen:
                seen.append(r.agent_name)
        return seen

    def clear(self):
        self._records.clear()
        self.updated.emit()