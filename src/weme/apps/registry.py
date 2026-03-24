from __future__ import annotations

from ..core.types import AppKind
from .wechat import WeChatAdapter
from .dingtalk import DingTalkAdapter
from .feishu import FeishuAdapter
from .base import AppAdapter

APP_ADAPTERS: dict[str, type[AppAdapter]] = {
    "wechat": WeChatAdapter,
    "dingtalk": DingTalkAdapter,
    "feishu": FeishuAdapter,
}


def get_app_adapter(app_key: AppKind) -> AppAdapter:
    if app_key not in APP_ADAPTERS:
        raise ValueError(f"Unsupported app: {app_key!r}. Choose from: {list(APP_ADAPTERS)}")
    return APP_ADAPTERS[app_key]()
