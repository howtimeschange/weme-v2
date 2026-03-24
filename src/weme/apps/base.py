"""Abstract base class for app adapters"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..core.types import AppSnapshot


class AppAdapter(ABC):
    """Abstract interface for messaging app adapters"""

    @property
    @abstractmethod
    def app_key(self) -> str:
        """Unique identifier for this app (e.g. 'wechat')"""
        ...

    @property
    @abstractmethod
    def app_names(self) -> tuple[str, ...]:
        """Display names / process names for this app"""
        ...

    @abstractmethod
    def activate(self) -> None:
        """Bring the app to the foreground"""
        ...

    @abstractmethod
    def send_text(self, text: str, press_enter: bool = True) -> None:
        """Send the given text via the app"""
        ...

    @abstractmethod
    def read_snapshot(self) -> AppSnapshot:
        """Capture the current state of the app window"""
        ...

    @abstractmethod
    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Extract the most recent inbound message from a snapshot"""
        ...
