from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


@dataclass
class ConversationState:
    snapshot_hash: str = ""
    last_sent_text: str = ""
    last_window_title: str = ""
    send_failure_count: int = 0
    high_risk_count: int = 0
    paused_until: str = ""


class StateStore:
    """内存 + 磁盘持久化的对话状态存储"""

    def __init__(self, state_file: Path | None = None) -> None:
        self._cache: dict[str, ConversationState] = {}
        self._state_file = state_file
        if state_file and state_file.exists():
            self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self._state_file.read_text(encoding="utf-8"))
            for key, val in data.items():
                self._cache[key] = ConversationState(**val)
        except Exception:
            pass

    def _save(self) -> None:
        if not self._state_file:
            return
        try:
            self._state_file.parent.mkdir(parents=True, exist_ok=True)
            data = {k: asdict(v) for k, v in self._cache.items()}
            self._state_file.write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    def load(self, key: str) -> ConversationState:
        return self._cache.get(key, ConversationState())

    def save(self, key: str, state: ConversationState) -> None:
        self._cache[key] = state
        self._save()

    def clear(self, key: str) -> None:
        self._cache.pop(key, None)
        self._save()
