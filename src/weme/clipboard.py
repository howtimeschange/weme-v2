"""Clipboard utilities"""

from __future__ import annotations

import subprocess
import sys


def read_clipboard() -> str:
    """Read text from the system clipboard"""
    if sys.platform == "darwin":
        try:
            result = subprocess.run(["pbpaste"], capture_output=True, text=True)
            return result.stdout
        except Exception:
            return ""
    elif sys.platform == "win32":
        try:
            import pyperclip

            return pyperclip.paste()
        except ImportError:
            pass
        try:
            import win32clipboard

            win32clipboard.OpenClipboard()
            try:
                return win32clipboard.GetClipboardData(win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except ImportError:
            pass
    return ""


def write_clipboard(text: str) -> None:
    """Write text to the system clipboard"""
    if sys.platform == "darwin":
        subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=True)
    elif sys.platform == "win32":
        try:
            import pyperclip

            pyperclip.copy(text)
            return
        except ImportError:
            pass
        try:
            import win32clipboard

            win32clipboard.OpenClipboard()
            try:
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardText(text, win32clipboard.CF_UNICODETEXT)
            finally:
                win32clipboard.CloseClipboard()
        except ImportError:
            pass
