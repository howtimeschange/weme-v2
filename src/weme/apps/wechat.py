"""WeChat app adapter"""

from __future__ import annotations

import re
import time

from ..core.types import AppSnapshot
from ..platform.factory import get_platform
from .base import AppAdapter

# Noise patterns to filter out from raw accessibility text
_NOISE_PATTERNS = [
    r"^\s*$",                           # empty lines
    r"^(微信|WeChat)$",                  # app name
    r"^\d{1,2}:\d{2}(:\d{2})?$",       # time stamps like "14:30"
    r"^(上午|下午|昨天|今天|星期[一二三四五六日]).*$",   # date headers
    r"^(消息|聊天|通讯录|发现|我)$",      # tab names
    r"^\[.*\]$",                         # system message brackets
]

_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]


def _looks_like_chat_text(line: str) -> bool:
    """Return True if the line looks like a real chat message"""
    stripped = line.strip()
    if not stripped:
        return False
    if len(stripped) < 2:
        return False
    for pattern in _NOISE_RE:
        if pattern.match(stripped):
            return False
    return True


def _clean_message_lines(raw: str) -> list[str]:
    """Filter and clean raw accessibility text into message lines"""
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if _looks_like_chat_text(stripped):
            cleaned.append(stripped)
    return cleaned


class WeChatAdapter(AppAdapter):
    """Adapter for WeChat (微信)"""

    def __init__(self) -> None:
        self._platform = get_platform()

    @property
    def app_key(self) -> str:
        return "wechat"

    @property
    def app_names(self) -> tuple[str, ...]:
        return ("微信", "WeChat")

    def activate(self) -> None:
        """Bring WeChat to the foreground"""
        self._platform.activate_app("WeChat")
        time.sleep(0.3)

    def send_text(self, text: str, press_enter: bool = True) -> None:
        """Write text to clipboard and paste into WeChat input"""
        self._platform.write_clipboard(text)
        time.sleep(0.1)
        self._platform.paste_and_send(press_enter=press_enter)

    def read_snapshot(self) -> AppSnapshot:
        """Read current WeChat window accessibility content"""
        raw = self._platform.read_accessibility("WeChat")
        lines = _clean_message_lines(raw)
        return AppSnapshot(
            app_name="WeChat",
            window_title="微信",
            raw_text=raw,
            message_lines=tuple(lines),
        )

    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Return the last non-empty message line as the latest inbound message"""
        for line in reversed(snapshot.message_lines):
            stripped = line.strip()
            if stripped:
                return stripped
        return ""
