"""DingTalk (钉钉) app adapter"""

from __future__ import annotations

import re
import time

from ..core.types import AppSnapshot
from ..platform.factory import get_platform
from .base import AppAdapter

_NOISE_PATTERNS = [
    r"^\s*$",
    r"^(钉钉|DingTalk)$",
    r"^\d{1,2}:\d{2}(:\d{2})?$",
    r"^(上午|下午|昨天|今天|星期[一二三四五六日]).*$",
    r"^(消息|联系人|工作|发现|我的)$",
    r"^\[.*系统.*\]$",
    r"^(已撤回消息|对方已撤回消息)$",
    # DingTalk-specific UI chrome
    r"^(发起会议|语音通话|视频通话)$",
    r"^(文件|图片|红包|转账)$",
]

_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]

# Patterns that indicate we're in the "work" focus area (DING messages, task notifications)
_WORK_AREA_MARKERS = [
    "DING",
    "待办",
    "审批",
    "日程",
    "打卡",
]


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


def _focus_raw_lines(lines: list[str], work_mode: bool = False, whitelist: list[str] | None = None) -> list[str]:
    """
    Focus on work-area lines when work_mode is True.
    In work_mode, only return messages from whitelisted contacts.
    """
    if not work_mode:
        return lines

    whitelist = whitelist or []
    if not whitelist:
        return lines

    focused = []
    for line in lines:
        for name in whitelist:
            if name in line:
                focused.append(line)
                break
        else:
            # Check if line is a non-work-area message
            is_work_noise = any(marker in line for marker in _WORK_AREA_MARKERS)
            if not is_work_noise:
                focused.append(line)

    return focused


class DingTalkAdapter(AppAdapter):
    """Adapter for DingTalk (钉钉)"""

    def __init__(
        self,
        work_mode: bool = False,
        whitelist: list[str] | None = None,
    ) -> None:
        self._platform = get_platform()
        self._work_mode = work_mode
        self._whitelist: list[str] = whitelist or []

    @property
    def app_key(self) -> str:
        return "dingtalk"

    @property
    def app_names(self) -> tuple[str, ...]:
        return ("钉钉", "DingTalk")

    def activate(self) -> None:
        """Bring DingTalk to the foreground"""
        self._platform.activate_app("DingTalk")
        time.sleep(0.3)

    def send_text(self, text: str, press_enter: bool = True) -> None:
        """Write text to clipboard and paste into DingTalk input"""
        self._platform.write_clipboard(text)
        time.sleep(0.1)
        self._platform.paste_and_send(press_enter=press_enter)

    def read_snapshot(self) -> AppSnapshot:
        """Read current DingTalk window accessibility content"""
        raw = self._platform.read_accessibility("DingTalk")
        all_lines = _clean_message_lines(raw)
        focused_lines = _focus_raw_lines(all_lines, self._work_mode, self._whitelist)
        return AppSnapshot(
            app_name="DingTalk",
            window_title="钉钉",
            raw_text=raw,
            message_lines=tuple(focused_lines),
        )

    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Return the last non-empty message line"""
        for line in reversed(snapshot.message_lines):
            stripped = line.strip()
            if stripped:
                return stripped
        return ""
