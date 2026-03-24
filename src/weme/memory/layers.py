"""Memory layers - short-term, long-term, and semantic retrieval"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from ..core.types import KnowledgeChunk

logger = logging.getLogger(__name__)

# Maximum number of raw messages to keep in short-term memory
SHORT_TERM_WINDOW = 20
# Maximum number of summaries to retain
MAX_SUMMARIES = 10


class ShortTermMemory:
    """
    In-memory ring buffer for recent messages in a conversation.
    Holds the last SHORT_TERM_WINDOW messages.
    """

    def __init__(self, window: int = SHORT_TERM_WINDOW) -> None:
        self._window = window
        self._buffer: list[dict[str, Any]] = []

    def push(self, role: str, content: str) -> None:
        entry = {"role": role, "content": content, "ts": time.time()}
        self._buffer.append(entry)
        if len(self._buffer) > self._window:
            self._buffer = self._buffer[-self._window:]

    def get_all(self) -> list[dict[str, Any]]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


class LongTermMemory:
    """
    File-based long-term memory using JSONL files per contact.
    Automatically manages rolling summaries.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def checkpoint_dir(self, contact_id: str) -> Path:
        d = self._base_dir / contact_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_checkpoint(
        self,
        contact_id: str,
        summary: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Save a conversation summary checkpoint"""
        cp_dir = self.checkpoint_dir(contact_id)
        ts = int(time.time())
        cp_file = cp_dir / f"{ts}.json"
        data = {
            "ts": ts,
            "contact_id": contact_id,
            "summary": summary,
            "metadata": metadata or {},
        }
        cp_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        # Prune old checkpoints
        checkpoints = sorted(cp_dir.glob("*.json"))
        if len(checkpoints) > MAX_SUMMARIES:
            for old in checkpoints[: len(checkpoints) - MAX_SUMMARIES]:
                old.unlink(missing_ok=True)

    def load_recent_summary(self, contact_id: str) -> str:
        """Load the most recent summary checkpoint for a contact"""
        cp_dir = self.checkpoint_dir(contact_id)
        checkpoints = sorted(cp_dir.glob("*.json"))
        if not checkpoints:
            return ""

        try:
            data = json.loads(checkpoints[-1].read_text(encoding="utf-8"))
            return data.get("summary", "")
        except Exception as e:
            logger.error(f"Failed to load checkpoint for {contact_id}: {e}")
            return ""


class SemanticMemory:
    """
    Simple keyword-based semantic retrieval from knowledge chunks.
    (A placeholder for future vector-based retrieval.)
    """

    def __init__(self, chunks: tuple[KnowledgeChunk, ...] = ()) -> None:
        self._chunks = chunks

    def retrieve(self, query: str, top_k: int = 3) -> tuple[KnowledgeChunk, ...]:
        """Return the top_k most relevant chunks for the query"""
        if not self._chunks:
            return ()

        # Simple keyword scoring
        query_words = set(query.lower().split())
        scored: list[tuple[float, KnowledgeChunk]] = []

        for chunk in self._chunks:
            combined = f"{chunk.title} {chunk.content}".lower()
            score = sum(1 for w in query_words if w in combined)
            if score > 0:
                scored.append((score, chunk))

        scored.sort(key=lambda x: x[0], reverse=True)
        return tuple(c for _, c in scored[:top_k])
