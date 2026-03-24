"""Platform factory - returns the correct platform implementation"""

import sys

from .base import PlatformAutomation


def get_platform() -> PlatformAutomation:
    """Return the appropriate platform implementation for the current OS"""
    if sys.platform == "darwin":
        from .macos import MacOSPlatform

        return MacOSPlatform()
    elif sys.platform == "win32":
        from .windows import WindowsPlatform

        return WindowsPlatform()
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
