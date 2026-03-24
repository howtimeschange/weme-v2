"""Windows platform automation implementation (best-effort, graceful fallback)"""

from __future__ import annotations

import time

from .base import PlatformAutomation


class WindowsPlatform(PlatformAutomation):
    """Windows platform automation using win32api and uiautomation"""

    def activate_app(self, app_name: str) -> None:
        """Bring the specified application to the foreground using win32gui"""
        try:
            import win32con
            import win32gui

            def _enum_handler(hwnd: int, result: list) -> None:
                title = win32gui.GetWindowText(hwnd)
                if app_name.lower() in title.lower():
                    result.append(hwnd)

            windows: list[int] = []
            win32gui.EnumWindows(_enum_handler, windows)

            if windows:
                hwnd = windows[0]
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
            else:
                # Try by class name
                hwnd = win32gui.FindWindow(None, app_name)
                if hwnd:
                    win32gui.SetForegroundWindow(hwnd)
                    time.sleep(0.5)
        except ImportError:
            # win32gui not available, try using subprocess
            try:
                import subprocess

                subprocess.Popen(["start", app_name], shell=True)
                time.sleep(1.0)
            except Exception:
                pass
        except Exception:
            pass

    def read_accessibility(self, process_name: str) -> str:
        """Read text from UI automation tree"""
        try:
            import uiautomation as auto

            texts: list[str] = []

            def _walk(ctrl: auto.Control, depth: int = 0) -> None:
                if depth > 10:
                    return
                try:
                    role = ctrl.ControlTypeName
                    if role in ("EditControl", "TextControl", "DocumentControl"):
                        value = ctrl.GetValuePattern().Value if hasattr(ctrl, "GetValuePattern") else ""
                        name = ctrl.Name or ""
                        if value:
                            texts.append(value)
                        elif name:
                            texts.append(name)
                except Exception:
                    pass
                try:
                    for child in ctrl.GetChildren():
                        _walk(child, depth + 1)
                except Exception:
                    pass

            # Find process window
            root = auto.GetRootControl()
            children = root.GetChildren()
            for child in children:
                try:
                    if process_name.lower() in (child.Name or "").lower():
                        _walk(child)
                        break
                except Exception:
                    continue

            return "\n".join(texts)

        except ImportError:
            return ""
        except Exception:
            return ""

    def write_clipboard(self, text: str) -> None:
        """Write text to the Windows clipboard"""
        # Try pyperclip first (cross-platform)
        try:
            import pyperclip

            pyperclip.copy(text)
            return
        except ImportError:
            pass

        # Try win32clipboard
        try:
            import win32clipboard

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
            return
        except ImportError:
            pass

        # Last resort: subprocess with PowerShell
        import subprocess

        subprocess.run(
            ["powershell", "-Command", f"Set-Clipboard -Value '{text.replace(chr(39), chr(34))}'"],
            check=False,
        )

    def paste_and_send(self, press_enter: bool = True) -> None:
        """Paste from clipboard and optionally press Enter"""
        try:
            import pyautogui

            pyautogui.hotkey("ctrl", "v")
            time.sleep(0.3)
            if press_enter:
                pyautogui.press("enter")
        except ImportError:
            # Fallback: use win32api
            try:
                import win32api
                import win32con

                # Ctrl+V
                win32api.keybd_event(win32con.VK_CONTROL, 0, 0, 0)
                win32api.keybd_event(ord("V"), 0, 0, 0)
                win32api.keybd_event(ord("V"), 0, win32con.KEYEVENTF_KEYUP, 0)
                win32api.keybd_event(win32con.VK_CONTROL, 0, win32con.KEYEVENTF_KEYUP, 0)
                time.sleep(0.3)
                if press_enter:
                    win32api.keybd_event(win32con.VK_RETURN, 0, 0, 0)
                    win32api.keybd_event(win32con.VK_RETURN, 0, win32con.KEYEVENTF_KEYUP, 0)
            except ImportError:
                pass
