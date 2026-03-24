"""Memory engine - builds MemoryContext from profiles and summaries"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from ..core.types import KnowledgeChunk, MemoryContext, ReplyRequest
from ..workspace import Workspace

logger = logging.getLogger(__name__)


class MemoryEngine:
    """
    Assembles MemoryContext from:
    - profiles/USER.md (user profile)
    - profiles/contacts/{contact_name}.md (contact card)
    - memory/summaries/{contact_id}.md (recent conversation summary)
    """

    def __init__(self, workspace: Workspace) -> None:
        self._ws = workspace

    def _read_file(self, path: Path) -> str:
        """Read a file safely, returning empty string if not found"""
        if path.exists():
            try:
                return path.read_text(encoding="utf-8").strip()
            except Exception as e:
                logger.warning(f"Failed to read {path}: {e}")
        return ""

    def build_memory_context(self, request: ReplyRequest) -> MemoryContext:
        """Assemble MemoryContext for the given request"""
        user_profile = self._read_file(self._ws.user_profile_path)
        contact_card = self._read_file(
            self._ws.contact_card_path(request.contact_name)
        )
        recent_summary = self._read_file(
            self._ws.summary_path(request.contact_id)
        )

        return MemoryContext(
            user_profile_text=user_profile,
            contact_card_text=contact_card,
            recent_summary_text=recent_summary,
            raw_evidence=(),
            sources=tuple(
                filter(
                    None,
                    [
                        str(self._ws.user_profile_path) if user_profile else "",
                        str(self._ws.contact_card_path(request.contact_name)) if contact_card else "",
                        str(self._ws.summary_path(request.contact_id)) if recent_summary else "",
                    ],
                )
            ),
        )

    def append_raw_message(
        self,
        contact_id: str,
        contact_name: str,
        role: str,
        content: str,
    ) -> None:
        """Append a message to the raw log for this contact"""
        raw_file = self._ws.raw_dir / f"{contact_id}.jsonl"
        raw_file.parent.mkdir(parents=True, exist_ok=True)

        import json

        entry = {
            "ts": time.time(),
            "contact_id": contact_id,
            "contact_name": contact_name,
            "role": role,
            "content": content,
        }
        try:
            with open(raw_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed to append raw message: {e}")

    def read_raw_messages(self, contact_id: str, limit: int = 50) -> list[dict]:
        """Read the last N raw messages for a contact"""
        raw_file = self._ws.raw_dir / f"{contact_id}.jsonl"
        if not raw_file.exists():
            return []

        import json

        lines = raw_file.read_text(encoding="utf-8").splitlines()
        results = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                try:
                    results.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return results

    def update_summary(self, contact_id: str, summary_text: str) -> None:
        """Write or overwrite the summary for a contact"""
        summary_path = self._ws.summary_path(contact_id)
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(summary_text, encoding="utf-8")
        logger.info(f"Updated summary for {contact_id}")
