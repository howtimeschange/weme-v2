"""Abstract base class for platform automation"""

from abc import ABC, abstractmethod


class PlatformAutomation(ABC):
    """Abstract platform automation interface"""

    @abstractmethod
    def activate_app(self, app_name: str) -> None:
        """Bring the specified application to the foreground"""
        ...

    @abstractmethod
    def read_accessibility(self, process_name: str) -> str:
        """Read text content from the accessibility tree of the given process"""
        ...

    @abstractmethod
    def write_clipboard(self, text: str) -> None:
        """Write text to the system clipboard"""
        ...

    @abstractmethod
    def paste_and_send(self, press_enter: bool = True) -> None:
        """Paste clipboard content into the focused input, then optionally press Enter"""
        ...
