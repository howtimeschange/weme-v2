"""Core type definitions for Weme v2"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

AppKind = Literal["wechat", "dingtalk", "feishu"]
ReplyMode = Literal["suggest", "auto", "hybrid"]
RiskLevel = Literal["low", "medium", "high"]


@dataclass(frozen=True)
class AppSnapshot:
    app_name: str
    window_title: str
    raw_text: str
    message_lines: tuple[str, ...]


@dataclass(frozen=True)
class ChatTurn:
    role: str  # "user" | "assistant"
    content: str


@dataclass(frozen=True)
class KnowledgeChunk:
    source: str
    title: str
    content: str


@dataclass(frozen=True)
class MemoryContext:
    user_profile_text: str = ""
    contact_card_text: str = ""
    recent_summary_text: str = ""
    raw_evidence: tuple[KnowledgeChunk, ...] = ()
    sources: tuple[str, ...] = ()


@dataclass
class ReplyRequest:
    contact_name: str
    contact_id: str
    chat_id: str
    latest_inbound: str
    conversation: tuple[ChatTurn, ...]
    workspace_root: Path
    profile: str
    max_reply_chars: int
    source_app: str
    window_title: str
    mode: ReplyMode = "hybrid"
    memory: MemoryContext | None = None
    knowledge_context: tuple[KnowledgeChunk, ...] = ()


@dataclass
class LLMResponse:
    text: str
    provider: str
    model: str
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_estimate: float = 0.0
    finish_reason: str = "stop"
