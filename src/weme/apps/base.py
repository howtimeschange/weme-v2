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
    def open_chat(self, name: str) -> bool:
        """Search for and open a chat with *name* (contact or group).

        Returns True if the chat was successfully opened, False otherwise.
        Implementations should activate the app, trigger the search UI,
        type the query, wait for results and click the first match.
        """
        ...

    @abstractmethod
    def send_text(self, text: str, press_enter: bool = True) -> None:
        """Send the given text via the app"""
        ...

    @abstractmethod
    def read_snapshot(self) -> AppSnapshot:
        """Capture the current state of the app window.

        The returned snapshot MUST include a `history` field with structured
        ChatTurn entries parsed from the visible chat window.
        """
        ...

    @abstractmethod
    def pick_latest_message(self, snapshot: AppSnapshot) -> str:
        """Extract the most recent inbound message from a snapshot"""
        ...
