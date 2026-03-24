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
# 搜索脚本只接收 appName（argv 1）
# 联系人名已由 Python 层通过 pbcopy 写入剪贴板，脚本直接 Cmd+V 粘贴
_WECHAT_OPEN_CHAT_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set didOpen to false

    tell application appName to activate
    delay 0.8

    tell application "System Events"
        tell process "WeChat"
            -- 打开搜索框
            keystroke "f" using command down
            delay 0.8
            -- 清空并粘贴（已由 Python pbcopy 写入剪贴板）
            keystroke "a" using command down
            delay 0.15
            keystroke "v" using command down
            delay 1.5

            -- 方案：直接 Enter 进入微信全局搜索结果页（不靠 ↓ 数量）
            key code 36
            delay 1.5

            -- 全局搜索结果页有多个分类 Tab（联系人/群聊/聊天记录等）
            -- 用 Accessibility 找到"群聊"Tab 并点击
            set foundGroupTab to false
            try
                set allBtns to every button of front window
                repeat with btn in allBtns
                    if title of btn is "群聊" then
                        click btn
                        set foundGroupTab to true
                        delay 0.5
                        exit repeat
                    end if
                end repeat
            end try

            -- 如果找不到 Tab（可能在 toolbar 里），用 Tab 键切换
            if not foundGroupTab then
                -- Tab×1 → 联系人, Tab×2 → 群聊
                key code 48
                delay 0.3
                key code 48
                delay 0.5
            end if

            -- 选第一个结果 ↓ + Enter
            key code 125
            delay 0.4
            key code 36
            delay 0.8
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

_DINGTALK_OPEN_CHAT_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set didOpen to false

    tell application appName to activate
    delay 0.8

    tell application "System Events"
        tell process "DingTalk"
            keystroke "f" using command down
            delay 0.8
            keystroke "a" using command down
            delay 0.15
            keystroke "v" using command down
            delay 1.5

            -- 钉钉搜索：第一项"你可能想找"已经是最匹配结果，直接 Enter 确认即可
            -- 不按 ↓，直接 Enter 选择"你可能想找"高亮项
            key code 36
            delay 0.8
            set didOpen to true
        end tell
    end tell
    return didOpen as string
end run
"""

_FEISHU_OPEN_CHAT_SCRIPT = """
on run argv
    set appName to item 1 of argv
    set didOpen to false

    tell application appName to activate
    delay 0.8

    tell application "System Events"
        tell process "Lark"
            -- 飞书全局搜索 Cmd+K
            keystroke "k" using command down
            delay 0.8
            keystroke "a" using command down
            delay 0.15
            keystroke "v" using command down
            delay 1.5
            key code 125
            delay 0.4
            key code 36
            delay 0.8
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
        # ① Python 层用 pbcopy 写剪贴板，保证中文 UTF-8 正确
        subprocess.run(
            ["pbcopy"],
            input=contact_name.encode("utf-8"),
            check=True,
        )
        time.sleep(0.1)

        # ② AppleScript 只负责 UI 操作（Cmd+F / Cmd+V / ↓ / Enter）
        #    不再传 contact_name，避免 AppleScript 字符集问题
        try:
            result = subprocess.run(
                ["osascript", "-e", script, app_name],
                capture_output=True, text=True, timeout=20,
            )
            out = result.stdout.strip().lower()
            if result.returncode != 0 or (result.stderr and "error" in result.stderr.lower()):
                self._last_error = result.stderr.strip()
            else:
                self._last_error = ""
            return out == "true"
        except Exception as exc:
            self._last_error = str(exc)
            return False

    # ── Accessibility read ────────────────────────────────────────────────

    def get_frontmost_window_title(self, process_name: str) -> str:
        """Return the title of the frontmost window for *process_name*."""
        script = f"""
tell application "System Events"
    tell process "{process_name}"
        try
            return title of front window
        end try
    end tell
end tell
return ""
"""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True, text=True, timeout=5,
            )
            return result.stdout.strip()
        except Exception:
            return ""

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
