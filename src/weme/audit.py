from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class AuditLogger:
    """审计日志记录器，写入结构化 JSON Lines"""

    def __init__(self, logs_dir: Path) -> None:
        logs_dir.mkdir(parents=True, exist_ok=True)
        self._reply_log = logs_dir / "reply_audit.log"
        self._risk_log = logs_dir / "risk_events.log"
        self._app_log = logs_dir / "app.log"

        # 配置标准 logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[
                logging.FileHandler(self._app_log, encoding="utf-8"),
                logging.StreamHandler(),
            ],
        )
        self.logger = logging.getLogger("weme")

    def _write(self, path: Path, data: dict[str, Any]) -> None:
        data.setdefault("ts", datetime.now(timezone.utc).isoformat())
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(data, ensure_ascii=False) + "\n")
        except Exception as exc:
            self.logger.warning(f"Failed to write audit log: {exc}")

    def log_reply(self, data: dict[str, Any]) -> None:
        self._write(self._reply_log, {"type": "reply", **data})

    def log_risk(self, data: dict[str, Any]) -> None:
        self._write(self._risk_log, {"type": "risk", **data})

    def log_event(self, event_type: str, data: dict[str, Any]) -> None:
        self._write(self._app_log, {"type": event_type, **data})
        self.logger.info(f"[{event_type}] {data.get('chat_id', '')} {data.get('contact_name', '')}")
