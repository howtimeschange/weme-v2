"""Feishu (飞书) app adapter"""

from __future__ import annotations

import re
import time

from ..core.types import AppSnapshot
from ..platform.factory import get_platform
from .base import AppAdapter
from .history_parser import parse_history

_NOISE_PATTERNS = [
    r"^\s*$",
    r"^(飞书|Feishu|Lark)$",
    r"^\d{1,2}:\d{2}(:\d{2})?$",
    r"^(上午|下午|昨天|今天|星期[一二三四五六日]).*$",
    r"^(消息|通讯录|工作台|会议|云文档|我的)$",
    r"^\[.*\]$",
    r"^(已撤回|撤回了一条消息)$",
    r"^(表情|图片|文件|截图|日历|任务|会议)$",
]
_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]

# Feishu process names to try in order
_FEISHU_PROCESSES = ("飞书", "Lark", "Feishu")


def _looks_like_chat_text(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 2:
        return False
    return not any(p.match(s) for p in _NOISE_RE)


def _clean_message_lines(raw: str) -> list[str]:
    return [l.strip() for l in raw.splitlines() if _looks_like_chat_text(l)]


class FeishuAdapter(AppAdapter):
    """Adapter for Feishu/Lark (飞书)"""

    def __init__(self, my_name: str = "") -> None:
        """
        Args:
            my_name: Local user's Feishu display name (for role="self").
        """
        self._platform = get_platform()
        self._my_name = my_name

    @property
    def app_key(self) -> str:
        return "feishu"

    @property
    def app_names(self) -> tuple[str, ...]:
        return ("飞书", "Feishu", "Lark")

    def activate(self) -> None:
        # platform 层会自动解析 "Lark" → 实际 App 名称
        self._platform.activate_app("Lark")

    def open_chat(self, name: str) -> bool:
        """Search for *name* in Feishu and open the conversation.

        Uses Cmd+K (Feishu's global search shortcut), types the name,
        then ↓ Enter to open the first result.

        Works for 1-on-1 chats and group chats.
        Returns True if the AppleScript ran without error.
        """
        return self._platform.open_chat_feishu(name)

    def send_text(self, text: str, press_enter: bool = True) -> None:
        self._platform.write_clipboard(text)
        time.sleep(0.1)
        self._platform.paste_and_send(press_enter=press_enter)

    def read_snapshot(self) -> AppSnapshot:
        """Capture current Feishu window and parse structured chat history."""
        raw = ""
        for name in _FEISHU_PROCESSES:
            raw = self._platform.read_accessibility(name)
            if raw.strip():
                break

        lines = _clean_message_lines(raw)
        history = parse_history(raw, known_self=self._my_name, max_turns=20)
        return AppSnapshot(
            app_name="Feishu",
            window_title="飞书",
            raw_text=raw,
            message_lines=tuple(lines),
            history=history,
        )

    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Return the latest message NOT sent by the local user."""
        if snapshot.history:
            for turn in reversed(snapshot.history):
                if turn.role != "self":
                    return turn.content
        for line in reversed(snapshot.message_lines):
            if line.strip():
                return line.strip()
        return ""
