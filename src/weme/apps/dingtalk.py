"""DingTalk (钉钉) app adapter"""

from __future__ import annotations

import re
import time

from ..core.types import AppSnapshot
from ..platform.factory import get_platform
from .base import AppAdapter
from .history_parser import parse_history

_NOISE_PATTERNS = [
    r"^\s*$",
    r"^(钉钉|DingTalk)$",
    r"^\d{1,2}:\d{2}(:\d{2})?$",
    r"^(上午|下午|昨天|今天|星期[一二三四五六日]).*$",
    r"^(消息|联系人|工作|发现|我的)$",
    r"^\[.*系统.*\]$",
    r"^(已撤回消息|对方已撤回消息)$",
    r"^(发起会议|语音通话|视频通话)$",
    r"^(文件|图片|红包|转账)$",
]
_NOISE_RE = [re.compile(p) for p in _NOISE_PATTERNS]

_WORK_AREA_MARKERS = ["DING", "待办", "审批", "日程", "打卡"]


def _looks_like_chat_text(line: str) -> bool:
    s = line.strip()
    if not s or len(s) < 2:
        return False
    return not any(p.match(s) for p in _NOISE_RE)


def _clean_message_lines(raw: str) -> list[str]:
    return [l.strip() for l in raw.splitlines() if _looks_like_chat_text(l)]


class DingTalkAdapter(AppAdapter):
    """Adapter for DingTalk (钉钉)"""

    def __init__(
        self,
        my_name: str = "",
        work_mode: bool = False,
        whitelist: list[str] | None = None,
    ) -> None:
        """
        Args:
            my_name: Local user's DingTalk display name (for role="self").
            work_mode: If True, filter out DING/system notifications.
            whitelist: Only include messages from these senders (work_mode only).
        """
        self._platform = get_platform()
        self._my_name = my_name
        self._work_mode = work_mode
        self._whitelist: list[str] = whitelist or []

    @property
    def app_key(self) -> str:
        return "dingtalk"

    @property
    def app_names(self) -> tuple[str, ...]:
        return ("钉钉", "DingTalk")

    def activate(self) -> None:
        self._platform.activate_app("DingTalk")
        time.sleep(0.3)

    def open_chat(self, name: str) -> bool:
        """Search for *name* in DingTalk and open the conversation.

        Uses Cmd+F to open DingTalk's search, types the name, then ↓ Enter.
        Works for both contacts and group chats.

        Returns True if the AppleScript ran without error.
        """
        return self._platform.open_chat_dingtalk(name)

    def send_text(self, text: str, press_enter: bool = True) -> None:
        self._platform.click_input_box("DingTalk")
        time.sleep(0.3)
        self._platform.write_clipboard(text)
        time.sleep(0.1)
        self._platform.paste_and_send(press_enter=press_enter)

    def read_snapshot(self) -> AppSnapshot:
        """Capture current DingTalk window and parse structured chat history."""
        raw = self._platform.read_accessibility("DingTalk")
        lines = _clean_message_lines(raw)

        # Optional: filter work-area noise in work_mode
        if self._work_mode and self._whitelist:
            lines = [
                l for l in lines
                if any(n in l for n in self._whitelist)
                or not any(m in l for m in _WORK_AREA_MARKERS)
            ]

        history = parse_history(raw, known_self=self._my_name, max_turns=20)
        return AppSnapshot(
            app_name="DingTalk",
            window_title="钉钉",
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
