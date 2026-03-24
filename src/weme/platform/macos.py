"""macOS platform automation implementation"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

from .base import PlatformAutomation

# ── 通用 Accessibility 抓取 ───────────────────────────────────────────────────

_WINDOW_ACCESSIBILITY_SCRIPT = """
on run argv
    set processName to item 1 of argv
    set outputText to ""
    try
        tell application "System Events"
            tell process processName
                set frontWin to front window
                set allElements to entire contents of frontWin
                repeat with elem in allElements
                    try
                        set elemRole to role of elem
                        if elemRole is "AXStaticText" or elemRole is "AXTextArea" \\
                                or elemRole is "AXTextField" or elemRole is "AXCell" then
                            set elemValue to value of elem
                            if elemValue is not missing value and elemValue is not "" then
                                set outputText to outputText & elemValue & linefeed
                            end if
                        end if
                    end try
                end repeat
            end tell
        end tell
    end try
    return outputText
end run
"""

_ACCESSIBILITY_DUMP_SCRIPT = """
on run argv
    set processName to item 1 of argv
    set outputText to ""
    try
        tell application "System Events"
            tell process processName
                set allElements to entire contents
                repeat with elem in allElements
                    try
                        set elemRole to role of elem
                        if elemRole is "AXStaticText" or elemRole is "AXTextArea" \\
                                or elemRole is "AXTextField" then
                            set elemValue to value of elem
                            if elemValue is not missing value and elemValue is not "" then
                                set outputText to outputText & elemValue & linefeed
                            end if
                        end if
                    end try
                end repeat
            end tell
        end tell
    end try
    return outputText
end run
"""

# ── 微信：搜索并打开聊天 ───────────────────────────────────────────────────────
# 微信 Mac 版搜索入口：Cmd+F（全局搜索），或点击搜索图标。
# 这里用 Cmd+F 触发搜索框，输入名字，等结果，然后点击第一条「聊天」类结果。
_WECHAT_OPEN_CHAT_SCRIPT = """
on run argv
    set contactName to item 1 of argv
    set didOpen to false

    tell application "WeChat" to activate
    delay 0.6

    tell application "System Events"
        tell process "WeChat"
            -- 触发全局搜索 Cmd+F
            keystroke "f" using command down
            delay 0.8

            -- 清空并输入联系人名
            keystroke "a" using command down
            delay 0.1
            keystroke contactName
            delay 1.2

            -- 尝试找到搜索结果列表中的第一个可点击行
            -- 微信搜索结果分组：联系人 / 群聊 / 聊天记录
            -- 直接按 Down + Enter 选第一个结果
            key code 125  -- down arrow
            delay 0.3
            key code 36   -- return / enter
            delay 0.4
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

# ── 钉钉：搜索并打开聊天 ───────────────────────────────────────────────────────
# 钉钉 Mac 版搜索：Cmd+F 或点击左上角搜索图标。
_DINGTALK_OPEN_CHAT_SCRIPT = """
on run argv
    set contactName to item 1 of argv
    set didOpen to false

    tell application "DingTalk" to activate
    delay 0.6

    tell application "System Events"
        tell process "DingTalk"
            keystroke "f" using command down
            delay 0.8

            keystroke "a" using command down
            delay 0.1
            keystroke contactName
            delay 1.2

            key code 125  -- down
            delay 0.3
            key code 36   -- enter
            delay 0.4
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

# ── 飞书：搜索并打开聊天 ───────────────────────────────────────────────────────
# 飞书 Mac 版搜索：Cmd+K（全局搜索）。
_FEISHU_OPEN_CHAT_SCRIPT = """
on run argv
    set contactName to item 1 of argv
    set didOpen to false

    -- 尝试多个进程名（中文/英文安装）
    set fsApp to missing value
    set processList to {"飞书", "Lark", "Feishu"}
    repeat with pName in processList
        try
            tell application pName to activate
            set fsApp to pName
            exit repeat
        end try
    end repeat
    if fsApp is missing value then return "false"
    delay 0.6

    tell application "System Events"
        tell process fsApp
            -- 飞书全局搜索快捷键
            keystroke "k" using command down
            delay 0.8

            keystroke "a" using command down
            delay 0.1
            keystroke contactName
            delay 1.2

            key code 125  -- down
            delay 0.3
            key code 36   -- enter
            delay 0.4
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

# ── 结构化聊天历史读取 ──────────────────────────────────────────────────────────
# 通过 AXGroup / AXList / AXCell 层级抓取带发言者名字的消息列表。
# 输出格式：每条消息 "SPEAKER\tCONTENT\tTIME"，以换行分隔。
_WECHAT_HISTORY_SCRIPT = """
on run argv
    set outputText to ""
    try
        tell application "System Events"
            tell process "WeChat"
                set frontWin to front window
                -- 微信聊天区是一个 AXScrollArea > AXWebArea 或 AXList
                -- 遍历所有 AXGroup，每个 group 代表一条消息
                set chatGroups to every group of frontWin
                repeat with grp in chatGroups
                    try
                        set grpTexts to {}
                        set grpElems to entire contents of grp
                        repeat with elem in grpElems
                            try
                                set elemRole to role of elem
                                if elemRole is "AXStaticText" or elemRole is "AXTextArea" then
                                    set v to value of elem
                                    if v is not missing value and v is not "" then
                                        set end of grpTexts to v
                                    end if
                                end if
                            end try
                        end repeat
                        if (count of grpTexts) > 0 then
                            set outputText to outputText & (do shell script "echo " & quoted form of (grpTexts as string)) & linefeed
                        end if
                    end try
                end repeat
            end tell
        end tell
    end try
    return outputText
end run
"""


class MacOSPlatform(PlatformAutomation):
    """macOS platform automation using AppleScript and pyautogui"""

    # ── App activation ────────────────────────────────────────────────────

    def activate_app(self, app_name: str) -> None:
        subprocess.run(["open", "-a", app_name], check=True)
        time.sleep(0.5)

    # ── Search & open chat ────────────────────────────────────────────────

    def open_chat_wechat(self, name: str) -> bool:
        """Search for *name* in WeChat and open the chat."""
        return self._run_open_chat(_WECHAT_OPEN_CHAT_SCRIPT, name)

    def open_chat_dingtalk(self, name: str) -> bool:
        """Search for *name* in DingTalk and open the chat."""
        return self._run_open_chat(_DINGTALK_OPEN_CHAT_SCRIPT, name)

    def open_chat_feishu(self, name: str) -> bool:
        """Search for *name* in Feishu/Lark and open the chat."""
        return self._run_open_chat(_FEISHU_OPEN_CHAT_SCRIPT, name)

    def _run_open_chat(self, script: str, name: str) -> bool:
        try:
            result = subprocess.run(
                ["osascript", "-e", script, name],
                capture_output=True, text=True, timeout=15,
            )
            out = result.stdout.strip().lower()
            return out == "true"
        except Exception:
            return False

    # ── Accessibility read ────────────────────────────────────────────────

    def read_accessibility(self, process_name: str) -> str:
        """Read flat text from the accessibility tree."""
        try:
            result = subprocess.run(
                ["osascript", "-e", _WINDOW_ACCESSIBILITY_SCRIPT, process_name],
                capture_output=True, text=True, timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            result2 = subprocess.run(
                ["osascript", "-e", _ACCESSIBILITY_DUMP_SCRIPT, process_name],
                capture_output=True, text=True, timeout=15,
            )
            return result2.stdout if result2.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    # ── Clipboard & send ──────────────────────────────────────────────────

    def write_clipboard(self, text: str) -> None:
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)

    def paste_and_send(self, press_enter: bool = True) -> None:
        try:
            import pyautogui
            pyautogui.hotkey("command", "v")
            time.sleep(0.3)
            if press_enter:
                pyautogui.press("enter")
        except ImportError:
            script = 'tell application "System Events" to keystroke "v" using command down'
            subprocess.run(["osascript", "-e", script])
            if press_enter:
                time.sleep(0.3)
                subprocess.run(["osascript", "-e",
                                 'tell application "System Events" to key code 36'])
