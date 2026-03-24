"""WeChat app adapter"""

from __future__ import annotations

import re
import time

from ..core.types import AppSnapshot, ChatTurn
from ..platform.factory import get_platform
from .base import AppAdapter
from .history_parser import parse_history

# Noise patterns for flat line filtering
_NOISE_PATTERNS = [
    r"^\s*$",
    r"^(微信|WeChat)$",
    r"^\d{1,2}:\d{2}(:\d{2})?$",
    r"^(上午|下午|昨天|今天|星期[一二三四五六日]).*$",
    r"^(消息|聊天|通讯录|发现|我)$",
    r"^\[.*\]$",
]
_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]


def _looks_like_chat_text(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 2:
        return False
    return not any(p.match(s) for p in _NOISE_RE)


def _clean_message_lines(raw: str) -> list[str]:
    return [l.strip() for l in raw.splitlines() if _looks_like_chat_text(l)]


class WeChatAdapter(AppAdapter):
    """Adapter for WeChat (微信)"""

    def __init__(self, my_name: str = "") -> None:
        """
        Args:
            my_name: The local user's WeChat display name, used to tag
                     outgoing messages with role="self" in history.
        """
        self._platform = get_platform()
        self._my_name = my_name

    @property
    def app_key(self) -> str:
        return "wechat"

    @property
    def app_names(self) -> tuple[str, ...]:
        return ("微信", "WeChat")

    def activate(self) -> None:
        self._platform.activate_app("WeChat")
        time.sleep(0.3)

    def open_chat(self, name: str) -> bool:
        """Search for *name* in WeChat and open the conversation.

        Uses Cmd+F to trigger WeChat's global search, types the contact/group
        name, then presses ↓ Enter to open the first result.

        Returns True if the AppleScript sequence ran without error.
        Note: WeChat does not expose a programmatic "open chat" API, so this
        relies on UI automation. Success does NOT guarantee an exact match —
        verify the window title after calling.
        """
        return self._platform.open_chat_wechat(name)

    def send_text(self, text: str, press_enter: bool = True) -> None:
        self._platform.click_input_box("WeChat")
        time.sleep(0.3)
        self._platform.write_clipboard(text)
        time.sleep(0.1)
        self._platform.paste_and_send(press_enter=press_enter)

    def read_snapshot(self) -> AppSnapshot:
        """Capture current WeChat window and parse structured chat history."""
        raw = self._platform.read_accessibility("WeChat")
        lines = _clean_message_lines(raw)
        history = parse_history(raw, known_self=self._my_name, max_turns=20)
        return AppSnapshot(
            app_name="WeChat",
            window_title="微信",
            raw_text=raw,
            message_lines=tuple(lines),
            history=history,
        )

    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Return the latest message NOT sent by the local user."""
        # Prefer structured history
        if snapshot.history:
            for turn in reversed(snapshot.history):
                if turn.role != "self":
                    return turn.content
        # Fallback to flat lines
        for line in reversed(snapshot.message_lines):
            if line.strip():
                return line.strip()
        return ""
