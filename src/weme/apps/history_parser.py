"""Shared utilities for parsing chat history from accessibility text.

Each app's raw accessibility dump is a flat sequence of text lines.
We parse it into structured ChatTurn objects using heuristics:

  - Lines that look like a person's display name (short, no punctuation)
    are treated as "speaker markers".
  - The lines immediately following are treated as that speaker's message.
  - A special sentinel MY_NAME (the local user's name, configurable) marks
    messages sent by the local user (role="self").

Accuracy is limited by what the OS accessibility API exposes — the structure
of accessibility trees differs between apps and OS versions, and WeChat's
custom renderer often yields partial output.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..core.types import ChatTurn

# ── Timestamp patterns ────────────────────────────────────────────────────────

_TS_PATTERNS = [
    re.compile(r"^(上午|下午|昨天|今天|星期[一二三四五六日])?[\s]*\d{1,2}:\d{2}(:\d{2})?$"),
    re.compile(r"^\d{4}[-/]\d{1,2}[-/]\d{1,2}"),
    re.compile(r"^(Yesterday|Today)\s+\d{1,2}:\d{2}"),
]

# ── Noise patterns (UI chrome) ────────────────────────────────────────────────

_UI_CHROME = re.compile(
    r"^(微信|WeChat|钉钉|DingTalk|飞书|Lark|Feishu"
    r"|消息|联系人|通讯录|工作台|发现|我|我的"
    r"|DING|待办|审批|日程|打卡"
    r"|表情|图片|文件|截图|日历|任务|会议"
    r"|发起会议|语音通话|视频通话|红包|转账"
    r"|已撤回|撤回了一条消息|对方已撤回消息"
    r")$"
)

# ── Speaker name heuristics ───────────────────────────────────────────────────
# A speaker name line is: short (≤20 chars), no trailing punctuation,
# no embedded spaces longer than Chinese names, not a timestamp.

_MAX_SPEAKER_LEN = 25
_SPEAKER_EXCLUDE = re.compile("[，。！？、；：\u201c\u201d\u2018\u2019【】《》\\[\\]…@#]")


def _is_timestamp(line: str) -> bool:
    return any(p.match(line.strip()) for p in _TS_PATTERNS)


def _is_ui_chrome(line: str) -> bool:
    return bool(_UI_CHROME.match(line.strip()))


def _is_speaker_name(line: str, known_self: str = "") -> bool:
    """Heuristically decide if this line is a speaker's display name."""
    s = line.strip()
    if not s:
        return False
    # known_self is always accepted as a speaker name regardless of length
    if known_self and s == known_self:
        return True
    if len(s) > _MAX_SPEAKER_LEN:
        return False
    if len(s) < 2:
        return False
    if _is_timestamp(s) or _is_ui_chrome(s):
        return False
    if _SPEAKER_EXCLUDE.search(s):
        return False
    # Names shouldn't look like sentences
    if s.endswith(("。", "？", "！", "…", ".", "?", "!")):
        return False
    return True


@dataclass
class _ParseState:
    turns: list[ChatTurn]
    current_speaker: str
    buffer: list[str]
    known_self: str

    def flush(self):
        content = " ".join(self.buffer).strip()
        if content:
            role = "self" if self.current_speaker == self.known_self else "user"
            self.turns.append(ChatTurn(
                role=role,
                content=content,
                speaker=self.current_speaker,
            ))
        self.buffer = []


def parse_history(
    raw: str,
    known_self: str = "",
    max_turns: int = 20,
) -> tuple[ChatTurn, ...]:
    """Parse flat accessibility text into a sequence of ChatTurns.

    Args:
        raw: Raw text from the accessibility tree.
        known_self: The display name of the local user (for role="self").
        max_turns: Maximum number of turns to return (most recent).

    Returns:
        Tuple of ChatTurns, oldest first, capped at *max_turns*.
    """
    state = _ParseState(turns=[], current_speaker="", buffer=[], known_self=known_self)
    lines = raw.splitlines()

    for line in lines:
        s = line.strip()
        if not s:
            continue
        # known_self is whitelisted even if it is a single character (e.g. "我")
        # and even if it matches UI chrome patterns.
        if known_self and s == known_self:
            if state.current_speaker and state.buffer:
                state.flush()
            state.current_speaker = s
            continue
        if len(s) < 2:
            continue
        if _is_ui_chrome(s):
            continue
        if _is_timestamp(s):
            continue

        if _is_speaker_name(s, known_self):
            if state.current_speaker and state.buffer:
                state.flush()
            state.current_speaker = s
        else:
            state.buffer.append(s)

    # Flush last
    if state.buffer:
        state.flush()

    turns = state.turns
    if len(turns) > max_turns:
        turns = turns[-max_turns:]
    return tuple(turns)


def history_to_context_string(history: tuple[ChatTurn, ...]) -> str:
    """Format chat history as a readable context string for LLM prompts."""
    if not history:
        return ""
    lines = []
    for turn in history:
        speaker = turn.speaker or ("我" if turn.role == "self" else "对方")
        lines.append(f"{speaker}: {turn.content}")
    return "\n".join(lines)
