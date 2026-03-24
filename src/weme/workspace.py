from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WorkspacePaths:
    root: Path
    config_dir: Path
    profiles_dir: Path
    memory_dir: Path
    data_dir: Path
    logs_dir: Path
    kb_dir: Path

    def ensure(self) -> None:
        for attr in ("config_dir", "profiles_dir", "memory_dir", "data_dir", "logs_dir", "kb_dir"):
            getattr(self, attr).mkdir(parents=True, exist_ok=True)

        # 子目录
        (self.memory_dir / "summaries").mkdir(exist_ok=True)
        (self.memory_dir / "raw").mkdir(exist_ok=True)
        (self.memory_dir / "checkpoints").mkdir(exist_ok=True)
        (self.memory_dir / "exports").mkdir(exist_ok=True)
        (self.profiles_dir / "contacts").mkdir(exist_ok=True)


def workspace_paths(root: Path | None = None) -> WorkspacePaths:
    r = root or Path.home() / ".weme"
    return WorkspacePaths(
        root=r,
        config_dir=r / "config",
        profiles_dir=r / "profiles",
        memory_dir=r / "memory",
        data_dir=r / "data",
        logs_dir=r / "logs",
        kb_dir=r / "kb",
    )
