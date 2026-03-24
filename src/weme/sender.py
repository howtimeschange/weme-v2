"""
批量发送执行引擎
--------------
- 立即发送 / 定时队列
- 图片发送（剪贴板 + pbpaste / pyautogui）
- 状态回写 Excel
"""
from __future__ import annotations

import subprocess
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

from .apps.registry import get_app_adapter
from .batch import (
    AppTarget, MsgType, SendTask, TaskStatus,
    parse_excel, write_status_back,
)


# ── 图片发送 ──────────────────────────────────────────────────────────────────

def _send_image_macos(image_path: str) -> None:
    """将图片写入剪贴板后粘贴发送（macOS）"""
    p = Path(image_path).expanduser()
    if not p.exists():
        raise FileNotFoundError(f"图片不存在: {p}")

    ext = p.suffix.lower()
    if ext in (".jpg", ".jpeg"):
        mime = "public.jpeg"
    elif ext == ".png":
        mime = "public.png"
    elif ext == ".gif":
        mime = "image/gif"
    else:
        mime = "public.png"

    # osascript 将图片写入剪贴板
    script = f"""
    set theFile to POSIX file "{p}"
    set theImage to (read theFile as «class PNGf»)
    set the clipboard to theImage
    """
    try:
        subprocess.run(["osascript", "-e", script],
                       capture_output=True, timeout=5)
    except Exception:
        # fallback: use pbcopy with tiff
        subprocess.run(
            f'osascript -e \'set the clipboard to (read (POSIX file "{p}") as «class PNGf»)\'',
            shell=True, timeout=5
        )

    time.sleep(0.3)

    try:
        import pyautogui
        pyautogui.hotkey("command", "v")
        time.sleep(0.4)
        pyautogui.press("enter")
    except ImportError:
        subprocess.run(["osascript", "-e",
                        'tell application "System Events" to keystroke "v" using command down'])
        time.sleep(0.4)
        subprocess.run(["osascript", "-e",
                        'tell application "System Events" to key code 36'])


# ── 单任务执行 ────────────────────────────────────────────────────────────────

class TaskExecutor:
    """执行单条 SendTask"""

    def __init__(
        self,
        on_status: Callable[[SendTask], None] | None = None,
    ):
        self.on_status = on_status or (lambda t: None)

    def execute(self, task: SendTask, variables: dict[str, str] | None = None) -> bool:
        """返回 True 表示成功"""
        task.status = TaskStatus.RUNNING
        self.on_status(task)

        try:
            adapter = get_app_adapter(task.app.value)
            plat = getattr(adapter, "_platform", None)

            # 激活 App 并搜索目标
            adapter.activate()
            time.sleep(0.5)

            ok = adapter.open_chat(task.target)
            if not ok:
                extra = getattr(plat, "_last_error", "") or ""
                hint = extra[:100] if extra else "请确认辅助功能权限已开启"
                raise RuntimeError(f"未能打开「{task.target}」: {hint}")

            # ── 验证窗口标题包含目标名称 ──────────────────────────────
            # 微信/钉钉聊天窗口标题格式各异，只要包含目标名即视为成功
            # 等待最多 5 秒
            process_map = {"wechat": "WeChat", "dingtalk": "DingTalk", "feishu": "Lark"}
            proc = process_map.get(task.app.value, "")
            verified = False
            if proc and plat and hasattr(plat, "get_frontmost_window_title"):
                for _ in range(10):  # 最多等 5 秒
                    title = plat.get_frontmost_window_title(proc)
                    if task.target in title:
                        verified = True
                        break
                    time.sleep(0.5)
                if not verified:
                    title = plat.get_frontmost_window_title(proc)
                    raise RuntimeError(
                        f"搜索后窗口标题不匹配：期望包含「{task.target}」，实际「{title or '(空)'}」\n"
                        f"请确认群聊/联系人名称与微信中完全一致（包括空格）"
                    )
            else:
                time.sleep(1.0)  # 无法验证时等待 1 秒

            # 发送文字
            if task.msg_type in (MsgType.TEXT, MsgType.BOTH):
                text = task.render_text(variables)
                if not text:
                    raise ValueError("文字内容为空")
                adapter.send_text(text, press_enter=True)
                time.sleep(0.5)

            # 发送图片
            if task.msg_type in (MsgType.IMAGE, MsgType.BOTH):
                if not task.image_path:
                    raise ValueError("图片路径为空")
                _send_image_macos(task.image_path)
                time.sleep(0.5)

            task.status = TaskStatus.DONE
            task.sent_at = datetime.now()
            self.on_status(task)
            return True

        except Exception as exc:
            task.status = TaskStatus.FAILED
            task.error = str(exc)[:120]
            self.on_status(task)
            return False


# ── 批量调度器 ────────────────────────────────────────────────────────────────

class BatchScheduler:
    """管理批量任务的调度和执行。

    立即任务：按顺序串行执行。
    定时任务：启动后台线程，在指定时间触发。
    """

    def __init__(
        self,
        tasks: list[SendTask],
        excel_path: Path | None = None,
        on_update: Callable[[SendTask], None] | None = None,
        variables: dict[str, str] | None = None,
        interval_secs: float = 2.0,
    ):
        self.tasks = tasks
        self.excel_path = excel_path
        self.variables = variables or {}
        self.interval = interval_secs
        self._on_update = on_update or (lambda t: None)
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._executor = TaskExecutor(on_status=self._task_updated)
        self._lock = threading.Lock()

    def _task_updated(self, task: SendTask):
        self._on_update(task)
        if self.excel_path:
            try:
                write_status_back(self.excel_path, self.tasks)
            except Exception:
                pass

    def start(self) -> None:
        """启动调度。立即任务同步执行；定时任务后台等待。"""
        now = datetime.now()

        immediate = [t for t in self.tasks if t.is_immediate and t.status == TaskStatus.PENDING]
        scheduled = [t for t in self.tasks if t.is_scheduled and t.status == TaskStatus.PENDING]

        # 立即任务串行
        for task in immediate:
            if self._stop.is_set():
                break
            self._executor.execute(task, self.variables)
            time.sleep(self.interval)

        # 定时任务各起一个线程
        for task in scheduled:
            task.status = TaskStatus.SCHEDULED
            self._task_updated(task)
            t = threading.Thread(
                target=self._wait_and_execute,
                args=(task,),
                daemon=True,
            )
            self._threads.append(t)
            t.start()

    def _wait_and_execute(self, task: SendTask):
        """等待到 send_at 时间后执行"""
        while not self._stop.is_set():
            now = datetime.now()
            if task.send_at and now >= task.send_at:
                self._executor.execute(task, self.variables)

                # 重复任务：更新 send_at 并重新等待
                if task.status == TaskStatus.DONE and task.repeat:
                    next_dt = self._next_repeat(task)
                    if next_dt:
                        task.send_at = next_dt
                        task.status = TaskStatus.SCHEDULED
                        task.error = ""
                        self._task_updated(task)
                        continue
                return

            remaining = (task.send_at - now).total_seconds() if task.send_at else 0
            time.sleep(min(10, max(0.5, remaining / 2)))

    @staticmethod
    def _next_repeat(task: SendTask) -> Optional[datetime]:
        base = task.sent_at or datetime.now()
        if task.repeat == "daily":
            return base.replace(
                day=base.day, hour=task.send_at.hour,  # type: ignore
                minute=task.send_at.minute, second=0, microsecond=0
            ) + timedelta(days=1)
        elif task.repeat == "weekly":
            return base + timedelta(weeks=1)
        elif task.repeat == "workday":
            next_day = base + timedelta(days=1)
            # 跳过周末
            while next_day.weekday() >= 5:
                next_day += timedelta(days=1)
            return next_day.replace(
                hour=task.send_at.hour, minute=task.send_at.minute,  # type: ignore
                second=0, microsecond=0
            )
        return None

    def stop(self):
        self._stop.set()

    def wait(self, timeout: float | None = None):
        for t in self._threads:
            t.join(timeout=timeout)

    @property
    def summary(self) -> dict[str, int]:
        from collections import Counter
        c = Counter(t.status for t in self.tasks)
        return {s.value: c[s] for s in TaskStatus}


# ── 便捷函数 ──────────────────────────────────────────────────────────────────

def run_excel_batch(
    excel_path: Path,
    *,
    variables: dict[str, str] | None = None,
    interval_secs: float = 2.0,
    on_update: Callable[[SendTask], None] | None = None,
    dry_run: bool = False,
) -> list[SendTask]:
    """
    一键从 Excel 读取任务并执行。

    Args:
        excel_path: Excel 文件路径
        variables: 文字内容中的变量替换，如 {"name": "张三"}
        interval_secs: 相邻立即任务之间的间隔（秒）
        on_update: 每条任务状态变化时的回调
        dry_run: True=只解析不发送（用于预览）

    Returns:
        执行完毕的 SendTask 列表
    """
    tasks = parse_excel(excel_path)
    if not tasks:
        return []

    if dry_run:
        for t in tasks:
            t.status = TaskStatus.SKIPPED
        return tasks

    scheduler = BatchScheduler(
        tasks=tasks,
        excel_path=excel_path,
        on_update=on_update,
        variables=variables,
        interval_secs=interval_secs,
    )
    scheduler.start()
    scheduler.wait()
    return tasks
