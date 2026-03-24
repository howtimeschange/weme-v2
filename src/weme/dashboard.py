from __future__ import annotations

import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from typing import Any

from .config import AssistantConfig
from .core.types import AppKind
from .daemon import AutoReplyDaemon
from .store import AppDataStore
from .workspace import workspace_paths

# 颜色主题
COLORS = {
    "bg": "#1e1e2e",
    "sidebar": "#181825",
    "panel": "#313244",
    "accent": "#89b4fa",
    "green": "#a6e3a1",
    "red": "#f38ba8",
    "yellow": "#f9e2af",
    "text": "#cdd6f4",
    "subtext": "#a6adc8",
    "border": "#45475a",
}

APP_ICONS = {
    "wechat": "💬",
    "dingtalk": "📌",
    "feishu": "🪶",
}

APP_LABELS = {
    "wechat": "微信",
    "dingtalk": "钉钉",
    "feishu": "飞书",
}


class WemeDashboard:
    """三栏式桌面工作台"""

    def __init__(self, config: AssistantConfig) -> None:
        self.config = config
        self.current_app: AppKind = "wechat"
        self.reply_queue: queue.Queue = queue.Queue()
        self.daemon: AutoReplyDaemon | None = None
        self.daemon_thread: threading.Thread | None = None
        self.stop_event = threading.Event()

        ws = workspace_paths(config.workspace_root)
        ws.ensure()
        self.data_store = AppDataStore(ws.data_dir / "app.db")

        self._build_ui()

    def _build_ui(self) -> None:
        self.root = tk.Tk()
        self.root.title("Weme 虾说 - 聊天助手")
        self.root.geometry("1200x800")
        self.root.configure(bg=COLORS["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("TFrame", background=COLORS["bg"])
        style.configure("TLabel", background=COLORS["bg"], foreground=COLORS["text"])
        style.configure("TButton", background=COLORS["panel"], foreground=COLORS["text"])
        style.configure("Accent.TButton", background=COLORS["green"], foreground="#1e1e2e")
        style.configure("Danger.TButton", background=COLORS["red"], foreground="#1e1e2e")

        # 主框架
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左栏 - 应用切换
        self._build_sidebar(main_frame)

        # 中栏 - 会话 + 消息
        self._build_middle(main_frame)

        # 右栏 - AI 建议
        self._build_right(main_frame)

        # 状态栏
        self._build_statusbar()

        # 启动 UI 更新定时器
        self.root.after(100, self._poll_queue)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sidebar = tk.Frame(parent, bg=COLORS["sidebar"], width=80)
        sidebar.pack(side=tk.LEFT, fill=tk.Y)
        sidebar.pack_propagate(False)

        # 标题
        title_lbl = tk.Label(
            sidebar, text="🦐", font=("Arial", 24), bg=COLORS["sidebar"], fg=COLORS["accent"]
        )
        title_lbl.pack(pady=(20, 10))

        # 应用按钮
        self.app_buttons: dict[AppKind, tk.Button] = {}
        for app_key in ("wechat", "dingtalk", "feishu"):
            btn = tk.Button(
                sidebar,
                text=f"{APP_ICONS[app_key]}\n{APP_LABELS[app_key]}",
                font=("Arial", 10),
                bg=COLORS["sidebar"],
                fg=COLORS["subtext"],
                relief=tk.FLAT,
                cursor="hand2",
                command=lambda k=app_key: self._switch_app(k),
                width=8,
                pady=8,
            )
            btn.pack(pady=4, padx=4, fill=tk.X)
            self.app_buttons[app_key] = btn

        self._highlight_app(self.current_app)

        # 底部控制
        tk.Frame(sidebar, bg=COLORS["sidebar"]).pack(expand=True)

        self.watch_btn = tk.Button(
            sidebar,
            text="▶\n监听",
            font=("Arial", 9),
            bg=COLORS["panel"],
            fg=COLORS["green"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._toggle_watch,
            width=8,
            pady=6,
        )
        self.watch_btn.pack(pady=4, padx=4, fill=tk.X)

    def _build_middle(self, parent: ttk.Frame) -> None:
        middle = tk.Frame(parent, bg=COLORS["bg"], width=500)
        middle.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # 标题栏
        header = tk.Frame(middle, bg=COLORS["panel"], height=40)
        header.pack(fill=tk.X)
        self.chat_title_lbl = tk.Label(
            header, text="选择一个应用开始", font=("Arial", 13, "bold"),
            bg=COLORS["panel"], fg=COLORS["text"],
        )
        self.chat_title_lbl.pack(side=tk.LEFT, padx=16, pady=8)

        # 消息区
        msg_frame = tk.Frame(middle, bg=COLORS["bg"])
        msg_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self.msg_text = scrolledtext.ScrolledText(
            msg_frame,
            font=("Arial", 11),
            bg=COLORS["bg"],
            fg=COLORS["text"],
            relief=tk.FLAT,
            state=tk.DISABLED,
            wrap=tk.WORD,
        )
        self.msg_text.pack(fill=tk.BOTH, expand=True)

        # 配置消息样式
        self.msg_text.tag_config("user", foreground=COLORS["text"])
        self.msg_text.tag_config("ai", foreground=COLORS["accent"])
        self.msg_text.tag_config("system", foreground=COLORS["subtext"], font=("Arial", 10, "italic"))

    def _build_right(self, parent: ttk.Frame) -> None:
        right = tk.Frame(parent, bg=COLORS["sidebar"], width=340)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        # AI 建议卡片
        suggest_header = tk.Label(
            right, text="✨ AI 建议", font=("Arial", 12, "bold"),
            bg=COLORS["sidebar"], fg=COLORS["accent"],
        )
        suggest_header.pack(padx=12, pady=(16, 6), anchor=tk.W)

        self.suggest_text = scrolledtext.ScrolledText(
            right,
            font=("Arial", 11),
            bg=COLORS["panel"],
            fg=COLORS["text"],
            relief=tk.FLAT,
            height=8,
            wrap=tk.WORD,
        )
        self.suggest_text.pack(fill=tk.X, padx=12, pady=4)

        # 操作按钮
        btn_frame = tk.Frame(right, bg=COLORS["sidebar"])
        btn_frame.pack(fill=tk.X, padx=12, pady=6)

        self.approve_btn = tk.Button(
            btn_frame,
            text="✓ Approve & Send",
            font=("Arial", 11, "bold"),
            bg=COLORS["green"],
            fg="#1e1e2e",
            relief=tk.FLAT,
            cursor="hand2",
            command=self._approve_suggestion,
            pady=8,
        )
        self.approve_btn.pack(fill=tk.X, pady=2)

        self.reject_btn = tk.Button(
            btn_frame,
            text="✗ Reject",
            font=("Arial", 11),
            bg=COLORS["panel"],
            fg=COLORS["red"],
            relief=tk.FLAT,
            cursor="hand2",
            command=self._reject_suggestion,
            pady=6,
        )
        self.reject_btn.pack(fill=tk.X, pady=2)

        # 风控提示
        self.risk_frame = tk.Frame(right, bg=COLORS["sidebar"])
        self.risk_frame.pack(fill=tk.X, padx=12, pady=4)
        self.risk_label = tk.Label(
            self.risk_frame, text="", font=("Arial", 10),
            bg=COLORS["sidebar"], fg=COLORS["yellow"],
            wraplength=300, justify=tk.LEFT,
        )
        self.risk_label.pack(anchor=tk.W)

        # 分隔线
        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12, pady=8)

        # 配置面板
        config_lbl = tk.Label(
            right, text="⚙ 配置", font=("Arial", 11, "bold"),
            bg=COLORS["sidebar"], fg=COLORS["accent"],
        )
        config_lbl.pack(padx=12, anchor=tk.W)

        mode_frame = tk.Frame(right, bg=COLORS["sidebar"])
        mode_frame.pack(fill=tk.X, padx=12, pady=4)
        tk.Label(mode_frame, text="回复模式:", bg=COLORS["sidebar"], fg=COLORS["subtext"]).pack(side=tk.LEFT)

        self.mode_var = tk.StringVar(value=self.config.default_mode)
        mode_menu = ttk.Combobox(
            mode_frame, textvariable=self.mode_var,
            values=["suggest", "auto", "hybrid"], state="readonly", width=10,
        )
        mode_menu.pack(side=tk.LEFT, padx=4)
        mode_menu.bind("<<ComboboxSelected>>", self._on_mode_change)

        # 日志
        ttk.Separator(right, orient=tk.HORIZONTAL).pack(fill=tk.X, padx=12, pady=8)
        log_lbl = tk.Label(
            right, text="📋 日志", font=("Arial", 11, "bold"),
            bg=COLORS["sidebar"], fg=COLORS["accent"],
        )
        log_lbl.pack(padx=12, anchor=tk.W)

        self.log_text = scrolledtext.ScrolledText(
            right,
            font=("Courier", 9),
            bg=COLORS["bg"],
            fg=COLORS["subtext"],
            relief=tk.FLAT,
            height=8,
            wrap=tk.WORD,
            state=tk.DISABLED,
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=12, pady=4)

        self._current_suggestion: str = ""

    def _build_statusbar(self) -> None:
        self.status_bar = tk.Label(
            self.root,
            text="就绪",
            font=("Arial", 9),
            bg=COLORS["panel"],
            fg=COLORS["subtext"],
            anchor=tk.W,
            padx=8,
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    def _highlight_app(self, app_key: AppKind) -> None:
        for k, btn in self.app_buttons.items():
            if k == app_key:
                btn.configure(bg=COLORS["accent"], fg="#1e1e2e")
            else:
                btn.configure(bg=COLORS["sidebar"], fg=COLORS["subtext"])

    def _switch_app(self, app_key: AppKind) -> None:
        self.current_app = app_key
        self._highlight_app(app_key)
        self.chat_title_lbl.configure(text=f"{APP_ICONS[app_key]} {APP_LABELS[app_key]}")
        self._log(f"切换到 {APP_LABELS[app_key]}")
        self._refresh_conversations()

        # 重启 daemon
        if self.daemon_thread and self.daemon_thread.is_alive():
            self._stop_daemon()
            self._start_daemon()

    def _refresh_conversations(self) -> None:
        try:
            convs = self.data_store.get_conversations(self.current_app, limit=20)
            self._add_message(f"已加载 {len(convs)} 个会话\n", "system")
        except Exception:
            pass

    def _toggle_watch(self) -> None:
        if self.daemon_thread and self.daemon_thread.is_alive():
            self._stop_daemon()
            self.watch_btn.configure(text="▶\n监听", fg=COLORS["green"])
            self._set_status("已停止监听")
        else:
            self._start_daemon()
            self.watch_btn.configure(text="⏹\n停止", fg=COLORS["red"])
            self._set_status(f"正在监听 {APP_LABELS[self.current_app]}...")

    def _start_daemon(self) -> None:
        self.stop_event.clear()
        self.config.default_mode = self.mode_var.get()
        self.daemon = AutoReplyDaemon(
            self.current_app,
            self.config,
            auto_send=False,  # GUI 模式默认不自动发送
            data_store=self.data_store,
        )

        def _daemon_callback() -> None:
            import time
            while not self.stop_event.is_set():
                try:
                    reply = self.daemon.step()
                    if reply:
                        self.reply_queue.put(("suggestion", reply))
                except Exception as exc:
                    self.reply_queue.put(("error", str(exc)))
                self.stop_event.wait(self.config.poll_interval)

        self.daemon_thread = threading.Thread(target=_daemon_callback, daemon=True)
        self.daemon_thread.start()

    def _stop_daemon(self) -> None:
        self.stop_event.set()
        if self.daemon_thread:
            self.daemon_thread.join(timeout=5)

    def _poll_queue(self) -> None:
        """从后台线程接收事件"""
        try:
            while True:
                event_type, data = self.reply_queue.get_nowait()
                if event_type == "suggestion":
                    self._show_suggestion(data)
                elif event_type == "error":
                    self._log(f"错误: {data}")
        except queue.Empty:
            pass
        self.root.after(500, self._poll_queue)

    def _show_suggestion(self, text: str) -> None:
        self._current_suggestion = text
        self.suggest_text.configure(state=tk.NORMAL)
        self.suggest_text.delete("1.0", tk.END)
        self.suggest_text.insert("1.0", text)
        self.suggest_text.configure(state=tk.DISABLED)
        self._add_message(f"[AI 建议] {text}\n", "ai")
        self._log(f"新建议: {text[:40]}...")
        self._set_status("收到新建议，请审核")

    def _approve_suggestion(self) -> None:
        text = self._current_suggestion
        if not text:
            return
        try:
            if self.daemon:
                self.daemon.adapter.send_text(text, press_enter=True)
            self._add_message(f"[已发送] {text}\n", "user")
            self._log("建议已批准并发送")
            self._set_status("已发送")
            self._clear_suggestion()
        except Exception as exc:
            messagebox.showerror("发送失败", str(exc))

    def _reject_suggestion(self) -> None:
        self._log("建议已拒绝")
        self._clear_suggestion()

    def _clear_suggestion(self) -> None:
        self._current_suggestion = ""
        self.suggest_text.configure(state=tk.NORMAL)
        self.suggest_text.delete("1.0", tk.END)
        self.suggest_text.configure(state=tk.DISABLED)
        self.risk_label.configure(text="")

    def _on_mode_change(self, _event: Any = None) -> None:
        new_mode = self.mode_var.get()
        self.config.default_mode = new_mode
        if self.daemon:
            self.daemon.mode = new_mode
        self._log(f"模式切换: {new_mode}")

    def _add_message(self, text: str, tag: str = "user") -> None:
        self.msg_text.configure(state=tk.NORMAL)
        self.msg_text.insert(tk.END, text, tag)
        self.msg_text.see(tk.END)
        self.msg_text.configure(state=tk.DISABLED)

    def _log(self, msg: str) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"[{ts}] {msg}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _set_status(self, msg: str) -> None:
        self.status_bar.configure(text=msg)

    def _on_close(self) -> None:
        self._stop_daemon()
        if self.data_store:
            self.data_store.close()
        self.root.destroy()

    def run(self) -> None:
        self._log("Weme 虾说已启动")
        self.root.mainloop()


def launch_dashboard(config: AssistantConfig) -> None:
    """启动 GUI 工作台"""
    app = WemeDashboard(config)
    app.run()
