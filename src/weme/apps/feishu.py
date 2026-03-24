"""Feishu (飞书) app adapter"""

from __future__ import annotations

import re
import time

from ..core.types import AppSnapshot
from ..platform.factory import get_platform
from .base import AppAdapter

_NOISE_PATTERNS = [
    r"^\s*$",
    r"^(飞书|Feishu|Lark)$",
    r"^\d{1,2}:\d{2}(:\d{2})?$",
    r"^(上午|下午|昨天|今天|星期[一二三四五六日]).*$",
    r"^(消息|通讯录|工作台|会议|云文档|我的)$",
    r"^\[.*\]$",
    r"^(已撤回|撤回了一条消息)$",
    # Feishu-specific UI chrome
    r"^(表情|图片|文件|截图|日历|任务|会议)$",
]

_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]


def _looks_like_chat_text(line: str) -> bool:
    """Return True if the line looks like actual chat content"""
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
    """Filter and clean raw text into message lines"""
    lines = raw.splitlines()
    cleaned = []
    for line in lines:
        stripped = line.strip()
        if _looks_like_chat_text(stripped):
            cleaned.append(stripped)
    return cleaned


class FeishuAdapter(AppAdapter):
    """Adapter for Feishu/Lark (飞书)"""

    def __init__(self) -> None:
        self._platform = get_platform()

    @property
    def app_key(self) -> str:
        return "feishu"

    @property
    def app_names(self) -> tuple[str, ...]:
        return ("飞书", "Feishu", "Lark")

    def activate(self) -> None:
        """Bring Feishu to the foreground"""
        # Try both Chinese and English app names
        try:
            self._platform.activate_app("飞书")
        except Exception:
            try:
                self._platform.activate_app("Lark")
            except Exception:
                self._platform.activate_app("Feishu")
        time.sleep(0.3)

    def send_text(self, text: str, press_enter: bool = True) -> None:
        """Write text to clipboard and paste into Feishu input"""
        self._platform.write_clipboard(text)
        time.sleep(0.1)
        self._platform.paste_and_send(press_enter=press_enter)

    def read_snapshot(self) -> AppSnapshot:
        """Read current Feishu window accessibility content"""
        # Try multiple process names
        raw = ""
        for name in ("飞书", "Lark", "Feishu"):
            raw = self._platform.read_accessibility(name)
            if raw.strip():
                break

        lines = _clean_message_lines(raw)
        return AppSnapshot(
            app_name="Feishu",
            window_title="飞书",
            raw_text=raw,
            message_lines=tuple(lines),
        )

    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Return the last non-empty message line"""
        for line in reversed(snapshot.message_lines):
            stripped = line.strip()
            if stripped:
                return stripped
        return ""
