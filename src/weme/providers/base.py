from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.types import ReplyRequest, LLMResponse


class ReplyProvider(ABC):
    """LLM 回复提供者抽象基类"""

    provider_name: str = "base"

    @abstractmethod
    def generate(self, request: ReplyRequest) -> str:
        """生成回复文本"""
        ...

    def generate_full(self, request: ReplyRequest) -> LLMResponse:
        """生成完整响应（含元数据）"""
        import time
        start = time.monotonic()
        text = self.generate(request)
        latency = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=text,
            provider=self.provider_name,
            model=getattr(self, "model", "unknown"),
            latency_ms=latency,
        )

    def health_check(self) -> bool:
        """健康检查"""
        return True
