from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from .core.types import MemoryContext, KnowledgeChunk
from .workspace import WorkspacePaths
from .defaults import default_profile

if TYPE_CHECKING:
    from .core.types import ReplyRequest


class MemoryEngine:
    """记忆系统：读写用户画像、联系人名片、会话摘要"""

    def __init__(self, workspace: WorkspacePaths) -> None:
        self.workspace = workspace

    # ─── 读取 ──────────────────────────────────────────────────────────────

    def _read_user_profile(self) -> str:
        path = self.workspace.profiles_dir / "USER.md"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return default_profile()

    def _read_contact_card(self, contact_name: str) -> str:
        safe_name = contact_name.replace("/", "_").replace("\\", "_")[:64]
        path = self.workspace.profiles_dir / "contacts" / f"{safe_name}.md"
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
        return ""

    def _read_recent_summary(self, contact_name: str, days: int = 7) -> str:
        safe_name = contact_name.replace("/", "_").replace("\\", "_")[:64]
        summaries_dir = self.workspace.memory_dir / "summaries"
        if not summaries_dir.exists():
            return ""
        # 读最近几个摘要文件
        files = sorted(
            (f for f in summaries_dir.glob(f"{safe_name}_*.md")),
            reverse=True,
        )[:days]
        if not files:
            return ""
        parts = []
        for f in files:
            try:
                parts.append(f.read_text(encoding="utf-8").strip())
            except Exception:
                pass
        return "\n\n---\n\n".join(parts)

    def _read_raw_evidence(self, contact_name: str, latest_message: str) -> tuple[KnowledgeChunk, ...]:
        """简单关键词检索原始记录"""
        safe_name = contact_name.replace("/", "_").replace("\\", "_")[:64]
        raw_dir = self.workspace.memory_dir / "raw"
        if not raw_dir.exists():
            return ()

        keywords = set(latest_message.split()[:10])
        results: list[KnowledgeChunk] = []

        for f in sorted(raw_dir.glob(f"{safe_name}_*.md"), reverse=True)[:10]:
            try:
                content = f.read_text(encoding="utf-8")
                # 简单关键词匹配
                if any(kw in content for kw in keywords if len(kw) >= 2):
                    results.append(KnowledgeChunk(
                        source=f.name,
                        title=f.stem,
                        content=content[:500],
                    ))
                    if len(results) >= 3:
                        break
            except Exception:
                pass

        return tuple(results)

    # ─── 构建上下文 ────────────────────────────────────────────────────────

    def build_memory_context(self, request: "ReplyRequest") -> MemoryContext:
        user_profile = self._read_user_profile()
        contact_card = self._read_contact_card(request.contact_name)
        recent_summary = self._read_recent_summary(request.contact_name)
        raw_evidence = self._read_raw_evidence(request.contact_name, request.latest_inbound)

        sources = tuple(
            chunk.source for chunk in raw_evidence
        )

        return MemoryContext(
            user_profile_text=user_profile,
            contact_card_text=contact_card,
            recent_summary_text=recent_summary,
            raw_evidence=raw_evidence,
            sources=sources,
        )

    # ─── 写入 ──────────────────────────────────────────────────────────────

    def append_raw_message(
        self,
        *,
        contact_name: str,
        content: str,
        role: str = "user",
        ts: str = "",
    ) -> None:
        from datetime import datetime, timezone
        safe_name = contact_name.replace("/", "_").replace("\\", "_")[:64]
        raw_dir = self.workspace.memory_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = raw_dir / f"{safe_name}_{today}.md"

        now_str = ts or datetime.now(timezone.utc).isoformat()
        with path.open("a", encoding="utf-8") as f:
            f.write(f"\n[{now_str}] [{role}]\n{content}\n")

    def update_contact_card(self, contact_name: str, facts: str) -> None:
        safe_name = contact_name.replace("/", "_").replace("\\", "_")[:64]
        path = self.workspace.profiles_dir / "contacts" / f"{safe_name}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(facts, encoding="utf-8")

    def save_summary(self, contact_name: str, summary: str, date_tag: str = "") -> None:
        from datetime import datetime, timezone
        safe_name = contact_name.replace("/", "_").replace("\\", "_")[:64]
        tag = date_tag or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = self.workspace.memory_dir / "summaries" / f"{safe_name}_{tag}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(summary, encoding="utf-8")
