from __future__ import annotations

import random

from ..core.types import ReplyRequest
from .base import ReplyProvider

_MOCK_REPLIES = [
    "收到，稍等一下。",
    "好的，我看一下。",
    "明白了，马上处理。",
    "嗯，知道了。",
    "这个我需要确认一下，稍后回复你。",
    "了解，谢谢。",
]


class MockReplyProvider(ReplyProvider):
    """本地测试用 mock provider，无需 API key"""

    provider_name = "mock"
    model = "mock-v1"

    def generate(self, request: ReplyRequest) -> str:
        return random.choice(_MOCK_REPLIES) + " [mock]"
