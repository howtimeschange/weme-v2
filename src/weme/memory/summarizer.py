"""Conversation summarizer using the AI provider"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..providers.base import ReplyProvider

from ..prompt import PromptBuilder

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """
    Summarizes raw conversation logs into concise summaries
    using the configured AI provider.
    """

    def __init__(self, provider: "ReplyProvider", prompts_dir: Path) -> None:
        self._provider = provider
        self._prompt_builder = PromptBuilder(prompts_dir)

    def summarize(self, raw_messages: list[dict]) -> str:
        """
        Summarize a list of raw message dicts into a concise text summary.
        Each dict should have 'role' and 'content' keys.
        """
        if not raw_messages:
            return ""

        # Format raw messages into readable text
        lines = []
        for msg in raw_messages:
            role = "用户" if msg.get("role") == "user" else "助理"
            content = msg.get("content", "")
            lines.append(f"{role}：{content}")

        raw_text = "\n".join(lines)
        prompt = self._prompt_builder.build_summarize_prompt(raw_text)

        try:
            # Build a minimal ReplyRequest for the summarization call
            from pathlib import Path as _Path

            from ..core.types import ChatTurn, ReplyRequest

            request = ReplyRequest(
                contact_name="",
                contact_id="",
                chat_id="",
                latest_inbound=prompt,
                conversation=(),
                workspace_root=_Path("."),
                profile="你是一个对话摘要助手，请生成简洁准确的摘要。",
                max_reply_chars=300,
                source_app="summarizer",
                window_title="",
            )
            summary = self._provider.generate(request)
            return summary
        except Exception as e:
            logger.error(f"Summarization failed: {e}")
            # Fallback: return last few messages as-is
            return "\n".join(lines[-5:])
