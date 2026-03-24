from __future__ import annotations

import time
from typing import Any

from ..core.types import ReplyRequest, LLMResponse
from .base import ReplyProvider


class ProviderRouter(ReplyProvider):
    """带 fallback 的 provider 路由器"""

    provider_name = "router"

    def __init__(
        self,
        primary: ReplyProvider,
        fallbacks: list[ReplyProvider] | None = None,
        max_retries: int = 2,
    ) -> None:
        self.primary = primary
        self.fallbacks = fallbacks or []
        self.max_retries = max_retries

    @property
    def model(self) -> str:
        return getattr(self.primary, "model", "unknown")

    def generate(self, request: ReplyRequest) -> str:
        providers = [self.primary] + self.fallbacks
        last_error: Exception | None = None

        for provider in providers:
            for attempt in range(self.max_retries):
                try:
                    result = provider.generate(request)
                    if result:
                        return result
                except Exception as exc:
                    last_error = exc
                    if attempt < self.max_retries - 1:
                        time.sleep(0.5 * (attempt + 1))  # 退避

        if last_error:
            raise last_error
        return ""

    def health_check(self) -> bool:
        return self.primary.health_check()


def build_provider(
    provider_type: str,
    *,
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    temperature: float = 0.7,
    timeout_ms: int = 12000,
    fallback_provider: str = "",
    fallback_api_key: str = "",
    fallback_model: str = "",
    fallback_base_url: str = "",
) -> ReplyProvider:
    """工厂方法：根据 provider 类型创建实例"""
    from .mock import MockReplyProvider
    from .openai_compat import OpenAICompatibleProvider, DeepSeekProvider, MiniMaxProvider
    from .anthropic import AnthropicCompatibleProvider

    kwargs: dict[str, Any] = {
        "temperature": temperature,
        "timeout_ms": timeout_ms,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if model:
        kwargs["model"] = model
    if base_url:
        kwargs["base_url"] = base_url

    provider_map = {
        "mock": lambda: MockReplyProvider(),
        "deepseek": lambda: DeepSeekProvider(**kwargs),
        "minimax": lambda: MiniMaxProvider(**kwargs),
        "anthropic": lambda: AnthropicCompatibleProvider(**kwargs),
        "anthropic-compatible": lambda: AnthropicCompatibleProvider(**kwargs),
        "claude": lambda: AnthropicCompatibleProvider(**kwargs),
    }

    if provider_type in provider_map:
        primary = provider_map[provider_type]()
    else:
        # 默认 OpenAI-compatible
        primary = OpenAICompatibleProvider(**kwargs)

    # 配置 fallback
    if fallback_provider and fallback_provider != provider_type:
        fallback_kwargs: dict[str, Any] = {"temperature": temperature, "timeout_ms": timeout_ms}
        if fallback_api_key:
            fallback_kwargs["api_key"] = fallback_api_key
        if fallback_model:
            fallback_kwargs["model"] = fallback_model
        if fallback_base_url:
            fallback_kwargs["base_url"] = fallback_base_url

        if fallback_provider in provider_map:
            fallback = provider_map[fallback_provider]()
        else:
            fallback = OpenAICompatibleProvider(**fallback_kwargs)

        return ProviderRouter(primary=primary, fallbacks=[fallback])

    return primary
