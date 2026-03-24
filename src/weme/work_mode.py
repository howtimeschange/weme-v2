from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.types import ReplyRequest


@dataclass
class DingTalkWorkModePolicy:
    """钉钉工作模式策略：白名单 + 工作时段"""

    enabled: bool = False
    whitelist_contacts: tuple[str, ...] = ()
    work_hours_start: int = 9
    work_hours_end: int = 18

    def _in_work_hours(self) -> bool:
        from datetime import datetime
        now = datetime.now()
        return self.work_hours_start <= now.hour < self.work_hours_end

    def allows_auto_send(self, request: "ReplyRequest") -> bool:
        if not self.enabled:
            return True

        # 工作时段限制
        if not self._in_work_hours():
            return False

        # 白名单限制
        if self.whitelist_contacts:
            return request.contact_name in self.whitelist_contacts

        return True
