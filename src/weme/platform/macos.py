"""macOS platform automation implementation"""

from __future__ import annotations

import subprocess
import time
from typing import Optional

from .base import PlatformAutomation

# AppleScript to dump accessibility text from a process
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
                        if elemRole is "AXStaticText" or elemRole is "AXTextArea" or elemRole is "AXTextField" then
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

# Faster, window-focused accessibility dump
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
                        if elemRole is "AXStaticText" or elemRole is "AXTextArea" or elemRole is "AXTextField" or elemRole is "AXCell" then
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


class MacOSPlatform(PlatformAutomation):
    """macOS platform automation using AppleScript and pyautogui"""

    def activate_app(self, app_name: str) -> None:
        """Bring the specified application to the foreground"""
        subprocess.run(["open", "-a", app_name], check=True)
        time.sleep(0.5)  # Give the app time to come to foreground

    def read_accessibility(self, process_name: str) -> str:
        """Read text from the accessibility tree via AppleScript"""
        try:
            result = subprocess.run(
                ["osascript", "-e", _WINDOW_ACCESSIBILITY_SCRIPT, process_name],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
            # Fallback to full process dump
            result2 = subprocess.run(
                ["osascript", "-e", _ACCESSIBILITY_DUMP_SCRIPT, process_name],
                capture_output=True,
                text=True,
                timeout=15,
            )
            return result2.stdout if result2.returncode == 0 else ""
        except subprocess.TimeoutExpired:
            return ""
        except Exception:
            return ""

    def write_clipboard(self, text: str) -> None:
        """Write text to the macOS clipboard using pbcopy"""
        subprocess.run(
            ["pbcopy"],
            input=text.encode("utf-8"),
            check=True,
        )

    def paste_and_send(self, press_enter: bool = True) -> None:
        """Paste from clipboard and optionally press Enter to send"""
        try:
            import pyautogui

            pyautogui.hotkey("command", "v")
            time.sleep(0.3)
            if press_enter:
                pyautogui.press("enter")
        except ImportError:
            # Fallback: use AppleScript key events
            script = 'tell application "System Events" to keystroke "v" using command down'
            subprocess.run(["osascript", "-e", script])
            if press_enter:
                time.sleep(0.3)
                enter_script = 'tell application "System Events" to key code 36'
                subprocess.run(["osascript", "-e", enter_script])
