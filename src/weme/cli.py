from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

app = typer.Typer(
    name="weme",
    help="虾说 - 接替人工处理微信/钉钉/飞书消息的桌面助手",
    add_completion=False,
)

APP_CHOICES = ["wechat", "dingtalk", "feishu"]


def _load_config(
    config_file: Path | None = None,
    workspace: Path | None = None,
) -> "AssistantConfig":
    from .config import AssistantConfig

    if config_file and config_file.exists():
        cfg = AssistantConfig.from_yaml(config_file)
    else:
        cfg = AssistantConfig.from_env()

    if workspace:
        cfg.workspace_root = workspace

    return cfg


@app.command()
def gui(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="工作区目录"),
    app_key: str = typer.Option("wechat", "--app", "-a", help="默认应用 (wechat/dingtalk/feishu)"),
) -> None:
    """打开桌面 GUI 工作台"""
    cfg = _load_config(config, workspace)
    from .dashboard import launch_dashboard
    launch_dashboard(cfg)


@app.command()
def watch(
    app_key: str = typer.Argument("wechat", help="要监听的应用 (wechat/dingtalk/feishu)"),
    auto_send: bool = typer.Option(False, "--auto-send", help="低风险时自动发送"),
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w", help="工作区目录"),
) -> None:
    """后台监听指定应用并持续生成回复建议"""
    if app_key not in APP_CHOICES:
        typer.echo(f"错误: 不支持的应用 {app_key!r}，请选择 {APP_CHOICES}", err=True)
        raise typer.Exit(1)

    cfg = _load_config(config, workspace)
    from .daemon import AutoReplyDaemon

    typer.echo(f"开始监听 {app_key}，模式: {cfg.default_mode}，自动发送: {auto_send}")
    daemon = AutoReplyDaemon(app_key, cfg, auto_send=auto_send)

    import threading
    stop_event = threading.Event()
    try:
        daemon.run(stop_event)
    except KeyboardInterrupt:
        typer.echo("\n已停止监听")
        stop_event.set()


@app.command()
def reply(
    message: str = typer.Argument(..., help="要回复的消息内容"),
    contact: str = typer.Option("测试联系人", "--contact", "-n", help="联系人名称"),
    app_key: str = typer.Option("wechat", "--app", "-a", help="应用 (wechat/dingtalk/feishu)"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """输入一条消息，生成并输出 AI 建议回复"""
    cfg = _load_config(config, workspace)
    from .providers.router import build_provider
    from .core.types import ReplyRequest, MemoryContext

    provider = build_provider(
        cfg.provider,
        model=cfg.model,
        api_key=cfg.api_key,
        base_url=cfg.base_url,
    )

    request = ReplyRequest(
        contact_name=contact,
        contact_id=contact,
        chat_id=contact,
        latest_inbound=message,
        conversation=(),
        workspace_root=cfg.workspace_root,
        profile=cfg.profile,
        max_reply_chars=cfg.max_reply_chars,
        source_app=app_key,
        window_title=contact,
        mode=cfg.default_mode,
        memory=MemoryContext(),
    )

    try:
        result = provider.generate(request)
        typer.echo(f"\n建议回复:\n{result}")
    except Exception as exc:
        typer.echo(f"错误: {exc}", err=True)
        raise typer.Exit(1)


@app.command()
def inspect(
    app_key: str = typer.Argument("wechat", help="要检查的应用"),
    raw: bool = typer.Option(False, "--raw", help="显示原始文本（调试用）"),
) -> None:
    """读取当前前台窗口快照（调试用）"""
    if app_key not in APP_CHOICES:
        typer.echo(f"错误: 不支持 {app_key!r}", err=True)
        raise typer.Exit(1)

    from .apps.registry import get_app_adapter

    adapter = get_app_adapter(app_key)
    snapshot = adapter.read_snapshot()

    typer.echo(f"窗口标题: {snapshot.window_title}")
    typer.echo(f"消息行数: {len(snapshot.message_lines)}")
    typer.echo(f"最新消息: {adapter.pick_latest_message(snapshot)}")

    if raw:
        typer.echo("\n--- 原始文本 ---")
        typer.echo(snapshot.raw_text[:2000])
    else:
        typer.echo("\n--- 消息列表 (最近 10 条) ---")
        for i, line in enumerate(snapshot.message_lines[-10:], 1):
            typer.echo(f"  {i}. {line}")


@app.command()
def send(
    text: str = typer.Argument(..., help="要发送的文本"),
    app_key: str = typer.Option("wechat", "--app", "-a", help="目标应用"),
    no_enter: bool = typer.Option(False, "--no-enter", help="不自动按 Enter"),
) -> None:
    """直接向当前激活的应用窗口发送文本"""
    if app_key not in APP_CHOICES:
        typer.echo(f"错误: 不支持 {app_key!r}", err=True)
        raise typer.Exit(1)

    from .apps.registry import get_app_adapter

    adapter = get_app_adapter(app_key)
    try:
        adapter.send_text(text, press_enter=not no_enter)
        typer.echo(f"已发送: {text[:50]}")
    except Exception as exc:
        typer.echo(f"发送失败: {exc}", err=True)
        raise typer.Exit(1)


@app.command()
def bootstrap(
    history_file: Path = typer.Argument(..., help="导出的聊天记录文件"),
    contact: str = typer.Option("", "--contact", "-n", help="联系人名称"),
    workspace: Optional[Path] = typer.Option(None, "--workspace", "-w"),
) -> None:
    """从导出的聊天记录回灌历史记忆"""
    if not history_file.exists():
        typer.echo(f"错误: 文件不存在 {history_file}", err=True)
        raise typer.Exit(1)

    ws_root = workspace or Path.home() / ".weme"
    from .workspace import workspace_paths
    from .memory import MemoryEngine

    ws = workspace_paths(ws_root)
    ws.ensure()
    engine = MemoryEngine(ws)

    content = history_file.read_text(encoding="utf-8", errors="replace")
    contact_name = contact or history_file.stem

    lines = content.splitlines()
    count = 0
    for line in lines:
        line = line.strip()
        if line:
            engine.append_raw_message(
                contact_name=contact_name,
                content=line,
                role="user",
            )
            count += 1

    typer.echo(f"已回灌 {count} 行记录到联系人 [{contact_name}]")


if __name__ == "__main__":
    app()
