from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AssistantConfig:
    # LLM 配置
    provider: str = "mock"
    model: str = ""
    api_key: str = ""
    base_url: str = ""
    temperature: float = 0.7
    timeout_ms: int = 12000

    # 运行模式
    default_mode: str = "hybrid"
    poll_interval: float = 3.0

    # 回复参数
    max_reply_chars: int = 120
    history_window: int = 10

    # 路径
    workspace_root: Path = field(default_factory=lambda: Path.home() / ".weme")
    kb_paths: tuple[Path, ...] = ()

    # 用户画像
    profile: str = ""

    # 钉钉工作模式
    dingtalk_work_mode: bool = False
    dingtalk_whitelist: tuple[str, ...] = ()

    # fallback
    fallback_provider: str = ""
    fallback_model: str = ""
    fallback_api_key: str = ""
    fallback_base_url: str = ""

    @classmethod
    def from_yaml(cls, path: Path) -> "AssistantConfig":
        import yaml, os
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        # 展开环境变量
        def _expand(v: Any) -> Any:
            if isinstance(v, str) and v.startswith("$"):
                return os.environ.get(v[1:], "")
            return v

        resolved: dict[str, Any] = {k: _expand(v) for k, v in data.items()}

        # 类型转换
        if "workspace_root" in resolved:
            resolved["workspace_root"] = Path(resolved["workspace_root"]).expanduser()
        if "kb_paths" in resolved:
            resolved["kb_paths"] = tuple(Path(p).expanduser() for p in resolved["kb_paths"])
        if "dingtalk_whitelist" in resolved:
            resolved["dingtalk_whitelist"] = tuple(resolved["dingtalk_whitelist"])

        return cls(**{k: v for k, v in resolved.items() if hasattr(cls, k)})

    @classmethod
    def from_env(cls) -> "AssistantConfig":
        """从环境变量加载（覆盖默认值）"""
        import os
        updates: dict[str, Any] = {}
        env_map = {
            "WEME_PROVIDER": "provider",
            "WEME_MODEL": "model",
            "WEME_API_KEY": "api_key",
            "WEME_BASE_URL": "base_url",
            "WEME_MODE": "default_mode",
            "OPENAI_API_KEY": "api_key",
            "ANTHROPIC_API_KEY": "api_key",
            "DEEPSEEK_API_KEY": "api_key",
        }
        for env_key, field_name in env_map.items():
            val = os.environ.get(env_key)
            if val:
                updates[field_name] = val
        return cls(**updates)
