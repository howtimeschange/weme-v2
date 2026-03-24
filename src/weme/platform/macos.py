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
# argv: 1=appName(真实App名), 2=contactName
# 微信进程名始终是 WeChat（CFBundleExecutable），和显示名无关。
_WECHAT_OPEN_CHAT_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set contactName to item 2 of argv
    set didOpen to false

    -- 先把联系人名写入剪贴板（避免 keystroke 经过输入法乱码）
    set the clipboard to contactName

    tell application appName to activate
    delay 0.8

    tell application "System Events"
        tell process "WeChat"
            -- 触发全局搜索 Cmd+F
            keystroke "f" using command down
            delay 0.8

            -- 清空搜索框，粘贴中文名称
            keystroke "a" using command down
            delay 0.1
            keystroke "v" using command down  -- Cmd+V 粘贴
            delay 1.2

            -- ↓ 选第一个结果，Enter 打开
            key code 125  -- down arrow
            delay 0.3
            key code 36   -- return / enter
            delay 0.6
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

# ── 钉钉：搜索并打开聊天 ───────────────────────────────────────────────────────
_DINGTALK_OPEN_CHAT_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set contactName to item 2 of argv
    set didOpen to false

    set the clipboard to contactName

    tell application appName to activate
    delay 0.8

    tell application "System Events"
        tell process "DingTalk"
            keystroke "f" using command down
            delay 0.8

            keystroke "a" using command down
            delay 0.1
            keystroke "v" using command down
            delay 1.2

            key code 125  -- down
            delay 0.3
            key code 36   -- enter
            delay 0.6
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

# ── 飞书：搜索并打开聊天 ───────────────────────────────────────────────────────
_FEISHU_OPEN_CHAT_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set contactName to item 2 of argv
    set didOpen to false

    set the clipboard to contactName

    tell application appName to activate
    delay 0.8

    tell application "System Events"
        tell process "Lark"
            -- 飞书全局搜索 Cmd+K
            keystroke "k" using command down
            delay 0.8

            keystroke "a" using command down
            delay 0.1
            keystroke "v" using command down
            delay 1.2

            key code 125  -- down
            delay 0.3
            key code 36   -- enter
            delay 0.6
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

    # ── App name resolution ───────────────────────────────────────────────

    # 缓存：bundle-executable-name → 真实 App 显示名
    _app_name_cache: dict[str, str] = {}

    # 已知别名表：各种常见叫法 → /Applications/ 下的真实名称（不含 .app）
    _APP_ALIASES: dict[str, list[str]] = {
        "WeChat":   ["微信 3", "微信", "WeChat"],
        "DingTalk": ["DingTalk", "钉钉"],
        "Feishu":   ["Lark", "飞书", "Feishu"],
        "Lark":     ["Lark", "飞书", "Feishu"],
    }

    def _resolve_app_name(self, name: str) -> str:
        """将进程名/别名解析为 /Applications/ 下实际存在的 App 名称。"""
        if name in self._app_name_cache:
            return self._app_name_cache[name]

        candidates = self._APP_ALIASES.get(name, [name])
        for candidate in candidates:
            app_path = f"/Applications/{candidate}.app"
            result = subprocess.run(
                ["test", "-d", app_path], capture_output=True
            )
            if result.returncode == 0:
                self._app_name_cache[name] = candidate
                return candidate

        # fallback：返回原始名称
        return name

    # ── App activation ────────────────────────────────────────────────────

    def activate_app(self, app_name: str) -> None:
        resolved = self._resolve_app_name(app_name)
        subprocess.run(["open", "-a", resolved], check=True)
        time.sleep(0.5)

    # ── Search & open chat ────────────────────────────────────────────────

    def open_chat_wechat(self, name: str) -> bool:
        """Search for *name* in WeChat and open the chat."""
        app_name = self._resolve_app_name("WeChat")
        return self._run_open_chat(_WECHAT_OPEN_CHAT_SCRIPT, app_name, name)

    def open_chat_dingtalk(self, name: str) -> bool:
        """Search for *name* in DingTalk and open the chat."""
        app_name = self._resolve_app_name("DingTalk")
        return self._run_open_chat(_DINGTALK_OPEN_CHAT_SCRIPT, app_name, name)

    def open_chat_feishu(self, name: str) -> bool:
        """Search for *name* in Feishu/Lark and open the chat."""
        app_name = self._resolve_app_name("Lark")
        return self._run_open_chat(_FEISHU_OPEN_CHAT_SCRIPT, app_name, name)

    def _run_open_chat(self, script: str, app_name: str, contact_name: str) -> bool:
        try:
            result = subprocess.run(
                ["osascript", "-e", script, app_name, contact_name],
                capture_output=True, text=True, timeout=20,
            )
            out = result.stdout.strip().lower()
            if result.returncode != 0 or (result.stderr and "error" in result.stderr.lower()):
                # 记录 stderr 方便调试，但不抛出——返回 False 让调用方处理
                self._last_error = result.stderr.strip()
            else:
                self._last_error = ""
            return out == "true"
        except Exception as exc:
            self._last_error = str(exc)
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
