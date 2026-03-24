from __future__ import annotations

from typing import Any

from ..core.types import ReplyRequest
from .base import ReplyProvider
from .openai_compat import _build_messages, _build_system_prompt


class AnthropicCompatibleProvider(ReplyProvider):
    """Anthropic Messages API provider（支持 Claude 系列）"""

    provider_name = "anthropic"

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-20250514",
        api_key: str = "",
        base_url: str = "https://api.anthropic.com/v1",
        temperature: float = 0.7,
        timeout_ms: int = 12000,
        max_tokens: int = 512,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout = timeout_ms / 1000
        self.max_tokens = max_tokens

    def generate(self, request: ReplyRequest) -> str:
        try:
            import httpx
        except ImportError as exc:
            raise RuntimeError("httpx is required. Install with: pip install httpx") from exc

        system_prompt = _build_system_prompt(request)
        messages = _build_messages(request)

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system_prompt,
            "messages": messages,
            "temperature": self.temperature,
        }

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/messages",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        content = data.get("content", [])
        for block in content:
            if block.get("type") == "text":
                return block.get("text", "").strip()
        return ""

    def health_check(self) -> bool:
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.base_url}/models",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                    },
                )
                return resp.status_code < 500
        except Exception:
            return False
