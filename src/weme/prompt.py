"""Prompt building from templates"""

from __future__ import annotations

import re
from pathlib import Path

from .core.types import MemoryContext, ReplyRequest


def _load_template(path: Path) -> str:
    """Load a prompt template file, returning empty string if not found"""
    if path.exists():
        return path.read_text(encoding="utf-8")
    return ""


def _fill_template(template: str, variables: dict[str, str]) -> str:
    """Replace {variable} placeholders in a template"""
    for key, value in variables.items():
        template = template.replace(f"{{{key}}}", value)
    return template


class PromptBuilder:
    """Builds prompts from template files + request context"""

    def __init__(self, prompts_dir: Path) -> None:
        self._prompts_dir = prompts_dir

    def build_system_prompt(self, request: ReplyRequest) -> str:
        """Build the system prompt from the system.md template and request context"""
        template = _load_template(self._prompts_dir / "system.md")

        memory = request.memory or MemoryContext()

        if not template:
            # Fallback inline system prompt
            parts = [request.profile or "你是一个专业友善的个人助理。"]
            if memory.user_profile_text:
                parts.append(f"\n## 用户信息\n{memory.user_profile_text}")
            if memory.contact_card_text:
                parts.append(f"\n## 联系人信息\n{memory.contact_card_text}")
            if memory.recent_summary_text:
                parts.append(f"\n## 历史摘要\n{memory.recent_summary_text}")
            return "\n".join(parts)

        return _fill_template(
            template,
            {
                "user_profile": memory.user_profile_text or "（未设置用户画像）",
                "contact_card": memory.contact_card_text or "（无联系人信息）",
                "recent_summary": memory.recent_summary_text or "（无历史摘要）",
                "max_reply_chars": str(request.max_reply_chars),
            },
        )

    def build_reply_prompt(self, request: ReplyRequest) -> str:
        """Build the reply prompt from reply.md template"""
        template = _load_template(self._prompts_dir / "reply.md")

        # Format conversation history
        history_lines = []
        for turn in request.conversation:
            prefix = "用户" if turn.role == "user" else "我"
            history_lines.append(f"{prefix}：{turn.content}")
        conversation_history = "\n".join(history_lines) if history_lines else "（无历史记录）"

        if not template:
            return (
                f"对话历史：\n{conversation_history}\n\n"
                f"最新消息：{request.latest_inbound}\n\n"
                f"请生成一个不超过 {request.max_reply_chars} 字的自然回复："
            )

        return _fill_template(
            template,
            {
                "conversation_history": conversation_history,
                "latest_message": request.latest_inbound,
                "max_reply_chars": str(request.max_reply_chars),
            },
        )

    def build_summarize_prompt(self, raw_messages: str) -> str:
        """Build a summarization prompt"""
        template = _load_template(self._prompts_dir / "summarize.md")

        if not template:
            return (
                f"请对以下对话记录进行简洁摘要（不超过200字），"
                f"保留主要话题、共识和待办事项：\n\n{raw_messages}"
            )

        return _fill_template(template, {"raw_messages": raw_messages})
