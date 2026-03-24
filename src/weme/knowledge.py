"""Knowledge base loading and chunking"""

from __future__ import annotations

import logging
from pathlib import Path

from .core.types import KnowledgeChunk

logger = logging.getLogger(__name__)


def load_knowledge_chunk(path: Path, workspace_root: Path) -> KnowledgeChunk | None:
    """Load a single knowledge base file as a KnowledgeChunk"""
    full_path = path if path.is_absolute() else workspace_root / path
    if not full_path.exists():
        logger.warning(f"Knowledge file not found: {full_path}")
        return None

    try:
        content = full_path.read_text(encoding="utf-8")
        # Use first non-empty line as title
        title = ""
        for line in content.splitlines():
            line = line.strip().lstrip("#").strip()
            if line:
                title = line
                break
        title = title or full_path.stem

        return KnowledgeChunk(
            source=str(full_path.relative_to(workspace_root) if workspace_root else full_path),
            title=title,
            content=content,
        )
    except Exception as e:
        logger.error(f"Failed to load knowledge file {full_path}: {e}")
        return None


def load_knowledge_base(
    kb_paths: list[str],
    workspace_root: Path,
) -> tuple[KnowledgeChunk, ...]:
    """Load multiple knowledge base files"""
    chunks: list[KnowledgeChunk] = []
    for path_str in kb_paths:
        chunk = load_knowledge_chunk(Path(path_str), workspace_root)
        if chunk is not None:
            chunks.append(chunk)
    return tuple(chunks)


def format_knowledge_for_prompt(chunks: tuple[KnowledgeChunk, ...]) -> str:
    """Format knowledge chunks into a string for inclusion in prompts"""
    if not chunks:
        return ""

    parts = []
    for chunk in chunks:
        parts.append(f"### {chunk.title}\n{chunk.content}")

    return "\n\n".join(parts)
