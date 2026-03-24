from __future__ import annotations

import json
import time
from typing import Any

from ..core.types import ReplyRequest
from .base import ReplyProvider


def _build_messages(request: ReplyRequest) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []

    # 历史对话
    for turn in request.conversation:
        messages.append({"role": turn.role, "content": turn.content})

    # 最新消息
    messages.append({"role": "user", "content": request.latest_inbound})

    return messages


def _build_system_prompt(request: ReplyRequest) -> str:
    parts: list[str] = []

    if request.profile:
        parts.append(request.profile)

    if request.memory:
        if request.memory.user_profile_text:
            parts.append(f"## 用户画像\n{request.memory.user_profile_text}")
        if request.memory.contact_card_text:
            parts.append(f"## 联系人信息\n{request.memory.contact_card_text}")
        if request.memory.recent_summary_text:
            parts.append(f"## 近期对话摘要\n{request.memory.recent_summary_text}")
        if request.memory.raw_evidence:
            evidence_texts = "\n\n".join(
                f"[{chunk.source}] {chunk.title}\n{chunk.content}"
                for chunk in request.memory.raw_evidence[:3]
            )
            parts.append(f"## 参考记忆\n{evidence_texts}")

    parts.append(
        f"## 回复要求\n"
        f"- 正在与 {request.contact_name} 对话\n"
        f"- 回复请简洁自然，不超过 {request.max_reply_chars} 字\n"
        f"- 不要解释你是 AI，直接以用户身份回复"
    )

    return "\n\n".join(parts)


class OpenAICompatibleProvider(ReplyProvider):
    """OpenAI Chat Completions 兼容 provider（支持 DeepSeek/MiniMax/自定义）"""

    provider_name = "openai_compat"

    def __init__(
        self,
        *,
        model: str = "gpt-4o",
        api_key: str = "",
        base_url: str = "https://api.openai.com/v1",
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
        messages = [{"role": "system", "content": system_prompt}] + _build_messages(request)

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(
                f"{self.base_url}/chat/completions",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()

        choices = data.get("choices", [])
        if not choices:
            return ""
        return choices[0].get("message", {}).get("content", "").strip()

    def health_check(self) -> bool:
        try:
            import httpx
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
                return resp.status_code < 500
        except Exception:
            return False


class DeepSeekProvider(OpenAICompatibleProvider):
    """DeepSeek provider"""
    provider_name = "deepseek"

    def __init__(self, *, model: str = "deepseek-chat", api_key: str = "", **kwargs: Any) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=kwargs.pop("base_url", "https://api.deepseek.com"),
            **kwargs,
        )


class MiniMaxProvider(OpenAICompatibleProvider):
    """MiniMax provider"""
    provider_name = "minimax"

    def __init__(self, *, model: str = "MiniMax-M2.5", api_key: str = "", **kwargs: Any) -> None:
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=kwargs.pop("base_url", "https://api.minimax.io/v1"),
            **kwargs,
        )
