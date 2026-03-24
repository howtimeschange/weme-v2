from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import ttk, messagebox
from typing import Optional

from .config import AssistantConfig
from .core.types import AppKind
from .daemon import AutoReplyDaemon
from .store import AppDataStore
from .workspace import workspace_paths

# ── Design tokens ────────────────────────────────────────────────────────────

C = {
    "bg":         "#0f1117",
    "surface":    "#1a1d27",
    "surface2":   "#242736",
    "surface3":   "#2e3148",
    "border":     "#363a52",
    "accent":     "#6c8cff",
    "accent_dim": "#3d50cc",
    "green":      "#4caf82",
    "green_dim":  "#2d6b4f",
    "red":        "#f27474",
    "red_dim":    "#8b2f2f",
    "yellow":     "#f2c04a",
    "text":       "#e8eaf0",
    "text2":      "#9ba3c0",
    "text3":      "#6b7294",
    "white":      "#ffffff",
}

FONT_UI    = ("Helvetica", 11)
FONT_TITLE = ("Helvetica", 13, "bold")
FONT_SMALL = ("Helvetica", 10)
FONT_MONO  = ("Courier", 10)
FONT_TAG   = ("Helvetica", 9)

APP_META = {
    "wechat":   {"label": "微信",  "icon": "💬", "color": "#1aad19"},
    "dingtalk": {"label": "钉钉",  "icon": "📌", "color": "#3296fa"},
    "feishu":   {"label": "飞书",  "icon": "🪶", "color": "#00b7c3"},
}


# ── Widgets ───────────────────────────────────────────────────────────────────

class FlatButton:
    """扁平风格按钮（不继承 tk.Frame 以避免 Tk9 _w 兼容问题）"""
    _PALETTES = {
        "default": (C["surface3"], C["border"],    C["text"]),
        "primary": (C["accent_dim"], C["accent"],  C["white"]),
        "success": (C["green_dim"],  C["green"],   C["white"]),
        "danger":  (C["red_dim"],    C["red"],      C["white"]),
    }

    def __init__(self, parent, text="", command=None, style="default",
                 width=120, height=36, **kw):
        self._text = text
        self._cmd = command
        self._style = style
        self._btn_w = width
        self._btn_h = height
        self._hover = False

        self._cv = tk.Canvas(parent, width=width, height=height,
                             bg=parent.cget("bg") if hasattr(parent, "cget") else C["bg"],
                             highlightthickness=0)
        self._cv.bind("<Enter>", lambda _: self._set_hover(True))
        self._cv.bind("<Leave>", lambda _: self._set_hover(False))
        self._cv.bind("<Button-1>", lambda _: self._click())
        self._draw()

    def pack(self, **kw):
        self._cv.pack(**kw)
        return self

    def grid(self, **kw):
        self._cv.grid(**kw)
        return self

    def _draw(self):
        cv = self._cv
        cv.delete("all")
        bg, border, fg = self._PALETTES.get(self._style, self._PALETTES["default"])
        if self._hover:
            bg = border
        w, h, r = self._btn_w, self._btn_h, 7
        cv.create_polygon(
            r, 0, w-r, 0, w, r, w, h-r, w-r, h, r, h, 0, h-r, 0, r,
            fill=bg, outline=border, smooth=True
        )
        cv.create_text(w//2, h//2, text=self._text, fill=fg,
                       font=(*FONT_UI[:1], FONT_UI[1], "bold"))

    def _set_hover(self, v):
        self._hover = v
        self._draw()

    def _click(self):
        if self._cmd:
            self._cmd()

    def configure_text(self, t):
        self._text = t
        self._draw()


class Divider(tk.Frame):
    def __init__(self, parent, orient="h", **kw):
        if orient == "h":
            super().__init__(parent, height=1, bg=C["border"], **kw)
        else:
            super().__init__(parent, width=1, bg=C["border"], **kw)


# ── Config Dialog ─────────────────────────────────────────────────────────────

class ConfigDialog(tk.Toplevel):

    PROVIDERS = [
        ("mock",         "Mock（本地测试，无需 Key）"),
        ("deepseek",     "DeepSeek"),
        ("minimax",      "MiniMax"),
        ("anthropic",    "Anthropic / Claude"),
        ("openai_compat","自定义 OpenAI-compatible"),
    ]
    MODELS = {
        "mock":         ["mock-v1"],
        "deepseek":     ["deepseek-chat", "deepseek-reasoner"],
        "minimax":      ["MiniMax-M2.5", "MiniMax-M1"],
        "anthropic":    ["claude-sonnet-4-20250514", "claude-haiku-4-20250514",
                         "claude-3-7-sonnet-20250219"],
        "openai_compat":["gpt-4o", "gpt-4o-mini"],
    }
    BASE_URLS = {
        "deepseek":     "https://api.deepseek.com",
        "minimax":      "https://api.minimax.io/v1",
        "anthropic":    "https://api.anthropic.com/v1",
        "openai_compat":"https://api.openai.com/v1",
    }

    def __init__(self, parent, config: AssistantConfig, on_save):
        super().__init__(parent)
        self.config = config
        self.on_save = on_save
        self.title("配置大模型")
        self.resizable(False, False)
        self.configure(bg=C["surface"])
        self.grab_set()
        self._build()
        self._center(parent)

    def _center(self, parent):
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - self.winfo_width()) // 2
        y = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

    def _lbl(self, parent, text):
        return tk.Label(parent, text=text, bg=C["surface"],
                        fg=C["text2"], font=FONT_SMALL, anchor="w")

    def _ent(self, parent, var, show=""):
        e = tk.Entry(parent, textvariable=var, bg=C["surface3"],
                     fg=C["text"], insertbackground=C["text"],
                     relief=tk.FLAT, font=FONT_UI, show=show,
                     highlightthickness=1, highlightbackground=C["border"],
                     highlightcolor=C["accent"])
        return e

    def _build(self):
        pad = {"padx": 24, "pady": 5}

        tk.Label(self, text="⚙  配置大模型", bg=C["surface"],
                 fg=C["text"], font=FONT_TITLE).pack(anchor="w", padx=24, pady=(20, 6))
        Divider(self).pack(fill="x", padx=20, pady=6)

        # Provider
        self._lbl(self, "Provider").pack(fill="x", padx=24)
        self._prov_var = tk.StringVar(value=self.config.provider)
        frame_p = tk.Frame(self, bg=C["surface"])
        frame_p.pack(fill="x", padx=24, pady=4)
        for val, label in self.PROVIDERS:
            tk.Radiobutton(
                frame_p, text=label, variable=self._prov_var, value=val,
                bg=C["surface"], fg=C["text"], selectcolor=C["surface3"],
                activebackground=C["surface"], activeforeground=C["accent"],
                font=FONT_SMALL, command=self._on_prov
            ).pack(anchor="w", pady=1)

        Divider(self).pack(fill="x", padx=20, pady=8)

        # Model
        self._lbl(self, "模型").pack(fill="x", padx=24)
        self._model_var = tk.StringVar(value=self.config.model or "")
        style = ttk.Style()
        style.configure("Dark.TCombobox",
            fieldbackground=C["surface3"], background=C["surface3"],
            foreground=C["text"], arrowcolor=C["text2"])
        self._combo = ttk.Combobox(self, textvariable=self._model_var,
                                   font=FONT_UI, style="Dark.TCombobox")
        self._combo.pack(fill="x", **pad)

        # API Key
        self._lbl(self, "API Key").pack(fill="x", padx=24)
        self._key_var = tk.StringVar(value=self.config.api_key or "")
        self._ent(self, self._key_var, show="•").pack(fill="x", **pad)

        # Base URL
        self._lbl(self, "Base URL（留空使用默认）").pack(fill="x", padx=24)
        self._url_var = tk.StringVar(value=self.config.base_url or "")
        self._ent(self, self._url_var).pack(fill="x", **pad)

        Divider(self).pack(fill="x", padx=20, pady=8)

        # params row
        row = tk.Frame(self, bg=C["surface"])
        row.pack(fill="x", padx=24, pady=4)
        left = tk.Frame(row, bg=C["surface"])
        left.pack(side="left", fill="x", expand=True, padx=(0, 8))
        right_ = tk.Frame(row, bg=C["surface"])
        right_.pack(side="right", fill="x", expand=True)

        self._lbl(left, "最大回复字数").pack(anchor="w")
        self._maxchar_var = tk.StringVar(value=str(self.config.max_reply_chars))
        self._ent(left, self._maxchar_var).pack(fill="x")

        self._lbl(right_, "轮询间隔（秒）").pack(anchor="w")
        self._interval_var = tk.StringVar(value=str(self.config.poll_interval))
        self._ent(right_, self._interval_var).pack(fill="x")

        Divider(self).pack(fill="x", padx=20, pady=10)

        btn_row = tk.Frame(self, bg=C["surface"])
        btn_row.pack(fill="x", padx=24, pady=(0, 20))
        FlatButton(btn_row, "取消", command=self.destroy,
                   style="default", width=90, height=34).pack(side="right", padx=(6,0))
        FlatButton(btn_row, "保存", command=self._save,
                   style="primary", width=90, height=34).pack(side="right")

        self._on_prov()

    def _on_prov(self):
        p = self._prov_var.get()
        models = self.MODELS.get(p, [])
        self._combo["values"] = models
        if models and self._model_var.get() not in models:
            self._model_var.set(models[0])
        url = self.BASE_URLS.get(p, "")
        if not self._url_var.get() or self._url_var.get() in self.BASE_URLS.values():
            self._url_var.set(url)

    def _save(self):
        try:
            maxc = int(self._maxchar_var.get())
            ivl = float(self._interval_var.get())
        except ValueError:
            messagebox.showerror("输入错误", "字数/间隔必须是数字", parent=self)
            return
        self.config.provider = self._prov_var.get()
        self.config.model = self._model_var.get().strip()
        self.config.api_key = self._key_var.get().strip()
        self.config.base_url = self._url_var.get().strip()
        self.config.max_reply_chars = maxc
        self.config.poll_interval = ivl
        self.on_save(self.config)
        self.destroy()


# ── Main Dashboard ────────────────────────────────────────────────────────────

class WemeDashboard:

    def __init__(self, config: AssistantConfig) -> None:
        self.config = config
        self.current_app: AppKind = "wechat"
        self.reply_queue: queue.Queue = queue.Queue()
        self.daemon: Optional[AutoReplyDaemon] = None
        self.daemon_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        self._watching = False
        self._current_suggestion = ""

        ws = workspace_paths(config.workspace_root)
        ws.ensure()
        self.data_store = AppDataStore(ws.data_dir / "app.db")
        self._build_ui()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.root = tk.Tk()
        self.root.title("Weme 虾说")
        self.root.geometry("1280x820")
        self.root.minsize(1000, 640)
        self.root.configure(bg=C["bg"])
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        style = ttk.Style()
        try: style.theme_use("clam")
        except: pass
        style.configure(".", background=C["bg"], foreground=C["text"])
        style.configure("Vertical.TScrollbar",
                         background=C["surface3"], troughcolor=C["surface"],
                         bordercolor=C["surface"], arrowcolor=C["text3"])

        outer = tk.Frame(self.root, bg=C["bg"])
        outer.pack(fill="both", expand=True)

        self._build_sidebar(outer)

        # 主内容区（聊天监听视图）
        self._main_view = tk.Frame(outer, bg=C["bg"])
        self._main_view.pack(side="left", fill="both", expand=True)
        self._build_topbar(self._main_view)
        Divider(self._main_view).pack(fill="x")
        self._build_content(self._main_view)

        # 批量任务视图（初始隐藏）
        self._batch_view = tk.Frame(outer, bg=C["bg"])
        self._build_batch_panel(self._batch_view)

        self._build_statusbar()
        self._build_right_panel(outer)
        self.root.after(500, self._poll_queue)

    def _build_sidebar(self, parent):
        sb = tk.Frame(parent, bg=C["surface"], width=76)
        sb.pack(side="left", fill="y")
        sb.pack_propagate(False)

        # logo
        tk.Label(sb, text="🦐", font=("Helvetica", 26), bg=C["surface"]).pack(pady=(18, 2))
        tk.Label(sb, text="虾说", bg=C["surface"], fg=C["accent"],
                 font=("Helvetica", 9, "bold")).pack()

        Divider(sb).pack(fill="x", padx=10, pady=10)

        # 聊天 App 按钮
        self._sidebar_btns: dict[str, tk.Frame] = {}
        for key, meta in APP_META.items():
            frame = tk.Frame(sb, bg=C["surface"], cursor="hand2")
            frame.pack(fill="x", pady=3)
            ic = tk.Label(frame, text=meta["icon"], font=("Helvetica", 20),
                          bg=C["surface"], fg=C["text2"])
            ic.pack()
            lb = tk.Label(frame, text=meta["label"], bg=C["surface"],
                          fg=C["text3"], font=FONT_TAG)
            lb.pack()
            for w in (frame, ic, lb):
                w.bind("<Button-1>", lambda _, k=key: self._switch_to_chat(k))
                w.bind("<Enter>",    lambda _, f=frame: self._sb_hover(f, True))
                w.bind("<Leave>",    lambda _, f=frame: self._sb_hover(f, False))
            self._sidebar_btns[key] = frame

        Divider(sb).pack(fill="x", padx=10, pady=8)

        # 批量任务按钮
        self._batch_sb_btn = tk.Frame(sb, bg=C["surface"], cursor="hand2")
        self._batch_sb_btn.pack(fill="x", pady=3)
        batch_ic = tk.Label(self._batch_sb_btn, text="📋", font=("Helvetica", 18),
                            bg=C["surface"], fg=C["text2"])
        batch_ic.pack()
        batch_lb = tk.Label(self._batch_sb_btn, text="批量", bg=C["surface"],
                            fg=C["text3"], font=FONT_TAG)
        batch_lb.pack()
        for w in (self._batch_sb_btn, batch_ic, batch_lb):
            w.bind("<Button-1>", lambda _: self._switch_to_batch())
            w.bind("<Enter>",    lambda _, f=self._batch_sb_btn: self._sb_hover(f, True))
            w.bind("<Leave>",    lambda _, f=self._batch_sb_btn: self._sb_hover(f, False))

        tk.Frame(sb, bg=C["surface"]).pack(expand=True)
        Divider(sb).pack(fill="x", padx=10, pady=8)

        # 配置入口
        cfg = tk.Frame(sb, bg=C["surface"], cursor="hand2")
        cfg.pack(pady=(0, 16))
        cfg_ic = tk.Label(cfg, text="⚙", font=("Helvetica", 18),
                          bg=C["surface"], fg=C["text3"])
        cfg_ic.pack()
        cfg_lb = tk.Label(cfg, text="配置", bg=C["surface"],
                          fg=C["text3"], font=FONT_TAG)
        cfg_lb.pack()
        for w in (cfg, cfg_ic, cfg_lb):
            w.bind("<Button-1>", lambda _: self._open_config())
            w.bind("<Enter>",    lambda _, f=cfg: self._sb_hover(f, True))
            w.bind("<Leave>",    lambda _, f=cfg: self._sb_hover(f, False))

        self._sb_select(self.current_app)

    def _sb_hover(self, frame, on):
        bg = C["surface2"] if on else C["surface"]
        frame.configure(bg=bg)
        for w in frame.winfo_children():
            try: w.configure(bg=bg)
            except: pass

    def _sb_select(self, app_key):
        # 取消激活批量按钮
        self._sb_deactivate_btn(self._batch_sb_btn)
        for k, f in self._sidebar_btns.items():
            active = k == app_key
            bg = C["surface3"] if active else C["surface"]
            f.configure(bg=bg)
            for w in f.winfo_children():
                try:
                    w.configure(bg=bg, fg=C["accent"] if active else C["text3"])
                except: pass

    def _sb_deactivate_btn(self, frame):
        frame.configure(bg=C["surface"])
        for w in frame.winfo_children():
            try: w.configure(bg=C["surface"], fg=C["text3"])
            except: pass

    def _switch_to_chat(self, app_key: str):
        """切换到聊天监听视图"""
        self._batch_view.pack_forget()
        self._main_view.pack(side="left", fill="both", expand=True)
        self._sb_deactivate_btn(self._batch_sb_btn)
        self._switch_app(app_key)

    def _switch_to_batch(self):
        """切换到批量任务视图"""
        self._main_view.pack_forget()
        self._batch_view.pack(side="left", fill="both", expand=True)
        # 高亮批量按钮，取消 app 按钮高亮
        for f in self._sidebar_btns.values():
            self._sb_deactivate_btn(f)
        self._batch_sb_btn.configure(bg=C["surface3"])
        for w in self._batch_sb_btn.winfo_children():
            try: w.configure(bg=C["surface3"], fg=C["accent"])
            except: pass
        self._set_status("批量任务模式")

    def _build_topbar(self, parent):
        bar = tk.Frame(parent, bg=C["surface"], height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)

        left = tk.Frame(bar, bg=C["surface"])
        left.pack(side="left", fill="y", padx=16)
        self._hdr_icon = tk.Label(left, text="💬", font=("Helvetica", 18),
                                   bg=C["surface"])
        self._hdr_icon.pack(side="left", pady=8)
        self._hdr_title = tk.Label(left, text="微信", font=FONT_TITLE,
                                    bg=C["surface"], fg=C["text"])
        self._hdr_title.pack(side="left", padx=8)
        self._hdr_sub = tk.Label(left, text="就绪", font=FONT_TAG,
                                  bg=C["surface"], fg=C["text3"])
        self._hdr_sub.pack(side="left")

        # ── 搜索联系人/群聊输入框 ──────────────────────────────────────────
        search_frame = tk.Frame(left, bg=C["surface3"],
                                highlightthickness=1,
                                highlightbackground=C["border"],
                                highlightcolor=C["accent"])
        search_frame.pack(side="left", padx=(20, 0), pady=12)
        tk.Label(search_frame, text="🔍", bg=C["surface3"],
                 fg=C["text3"], font=("Helvetica", 12)).pack(side="left", padx=(6, 2))
        self._search_var = tk.StringVar()
        self._search_entry = tk.Entry(
            search_frame, textvariable=self._search_var,
            bg=C["surface3"], fg=C["text"], insertbackground=C["text"],
            relief=tk.FLAT, font=FONT_UI, width=18
        )
        self._search_entry.pack(side="left", padx=(0, 6), pady=4)
        self._search_entry.bind("<Return>", lambda _: self._open_chat_from_search())
        self._search_entry.bind("<KP_Enter>", lambda _: self._open_chat_from_search())

        right = tk.Frame(bar, bg=C["surface"])
        right.pack(side="right", padx=16, fill="y")

        # 模式选择
        mode_row = tk.Frame(right, bg=C["surface"])
        mode_row.pack(side="right", fill="y", padx=(12, 0))
        tk.Label(mode_row, text="模式", bg=C["surface"],
                 fg=C["text3"], font=FONT_TAG).pack(side="left", padx=(0, 4))
        self._mode_var = tk.StringVar(value=self.config.default_mode)
        mode_cb = ttk.Combobox(mode_row, textvariable=self._mode_var,
                               values=["suggest", "auto", "hybrid"],
                               state="readonly", width=8, font=FONT_SMALL)
        mode_cb.pack(side="left")
        mode_cb.bind("<<ComboboxSelected>>", lambda _: self._on_mode_change())

        # 监听按钮
        self._watch_cv = tk.Canvas(right, width=100, height=32,
                                    bg=C["surface"], highlightthickness=0)
        self._watch_cv.pack(side="right", pady=10)
        self._watch_cv.bind("<Button-1>", lambda _: self._toggle_watch())
        self._draw_watch_btn()

    def _draw_watch_btn(self):
        cv = self._watch_cv
        cv.delete("all")
        w, h, r = 100, 32, 6
        watching = self._watching
        bg     = C["green_dim"] if watching else C["surface3"]
        border = C["green"]     if watching else C["border"]
        text   = "⏹  停止"     if watching else "▶  监听"
        cv.create_polygon(r,0, w-r,0, w,r, w,h-r, w-r,h, r,h, 0,h-r, 0,r,
                          fill=bg, outline=border, smooth=True)
        cv.create_text(w//2, h//2, text=text,
                       fill=C["green"] if watching else C["text"],
                       font=(*FONT_SMALL[:1], FONT_SMALL[1]))

    def _build_content(self, parent):
        content = tk.Frame(parent, bg=C["bg"])
        content.pack(fill="both", expand=True)

        # 会话列表
        conv_pane = tk.Frame(content, bg=C["surface"], width=210)
        conv_pane.pack(side="left", fill="y")
        conv_pane.pack_propagate(False)

        tk.Label(conv_pane, text="会话列表", bg=C["surface"],
                 fg=C["text2"], font=FONT_SMALL, padx=12, pady=8,
                 anchor="w").pack(fill="x")
        Divider(conv_pane).pack(fill="x")

        self._conv_frame = tk.Frame(conv_pane, bg=C["surface"])
        self._conv_frame.pack(fill="both", expand=True)
        self._no_conv_lbl = tk.Label(
            self._conv_frame,
            text="还没有会话\n开始监听后自动出现",
            bg=C["surface"], fg=C["text3"],
            font=FONT_SMALL, justify="center"
        )
        self._no_conv_lbl.pack(expand=True)

        Divider(content, orient="v").pack(side="left", fill="y")

        # 消息流
        msg_pane = tk.Frame(content, bg=C["bg"])
        msg_pane.pack(side="left", fill="both", expand=True)

        self._msg_canvas = tk.Canvas(msg_pane, bg=C["bg"], highlightthickness=0)
        sb_v = ttk.Scrollbar(msg_pane, orient="vertical",
                              command=self._msg_canvas.yview)
        self._msg_inner = tk.Frame(self._msg_canvas, bg=C["bg"])
        self._msg_inner.bind(
            "<Configure>",
            lambda e: self._msg_canvas.configure(
                scrollregion=self._msg_canvas.bbox("all"))
        )
        self._msg_canvas.create_window((0, 0), window=self._msg_inner, anchor="nw")
        self._msg_canvas.configure(yscrollcommand=sb_v.set)
        self._msg_canvas.pack(side="left", fill="both", expand=True)
        sb_v.pack(side="right", fill="y")

        # 欢迎提示
        self._add_msg("👋  欢迎使用虾说，点击「▶ 监听」开始", "system")

    # ── 批量任务面板 ──────────────────────────────────────────────────────────

    def _build_batch_panel(self, parent):
        """批量发送任务面板"""
        import tkinter.filedialog as fd

        # 顶部标题栏
        hdr = tk.Frame(parent, bg=C["surface"], height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="📋  批量发送任务", font=FONT_TITLE,
                 bg=C["surface"], fg=C["text"]).pack(side="left", padx=16, pady=12)

        btn_row = tk.Frame(hdr, bg=C["surface"])
        btn_row.pack(side="right", padx=16, pady=10)

        FlatButton(btn_row, "⬇  生成模版", command=self._batch_gen_template,
                   style="default", width=110, height=30).pack(side="left", padx=4)
        FlatButton(btn_row, "📂  导入表格", command=self._batch_import,
                   style="primary", width=110, height=30).pack(side="left", padx=4)

        Divider(parent).pack(fill="x")

        # 文件路径显示
        path_bar = tk.Frame(parent, bg=C["surface2"])
        path_bar.pack(fill="x", padx=12, pady=6)
        self._batch_path_var = tk.StringVar(value="尚未导入任务表格")
        tk.Label(path_bar, textvariable=self._batch_path_var,
                 bg=C["surface2"], fg=C["text2"], font=FONT_SMALL,
                 anchor="w").pack(side="left", padx=8, pady=4)

        # 任务列表（Treeview）
        tree_frame = tk.Frame(parent, bg=C["bg"])
        tree_frame.pack(fill="both", expand=True, padx=12, pady=4)

        cols = ("app", "target", "type", "preview", "send_at", "repeat", "status")
        col_names = ("应用", "联系人/群聊", "类型", "内容预览", "发送时间", "重复", "状态")
        col_widths = (60, 140, 80, 200, 120, 60, 70)

        style = ttk.Style()
        style.configure("Batch.Treeview",
            background=C["surface"], fieldbackground=C["surface"],
            foreground=C["text"], rowheight=24,
            borderwidth=0, font=("Helvetica", 10))
        style.configure("Batch.Treeview.Heading",
            background=C["surface3"], foreground=C["text2"],
            font=("Helvetica", 10, "bold"), borderwidth=0)
        style.map("Batch.Treeview",
            background=[("selected", C["accent_dim"])],
            foreground=[("selected", C["white"])])

        self._batch_tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            style="Batch.Treeview"
        )
        for col, name, w in zip(cols, col_names, col_widths):
            self._batch_tree.heading(col, text=name)
            self._batch_tree.column(col, width=w, minwidth=40, anchor="center")
        self._batch_tree.column("preview", anchor="w")
        self._batch_tree.column("target", anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical",
                            command=self._batch_tree.yview)
        self._batch_tree.configure(yscrollcommand=vsb.set)
        self._batch_tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        # 底部操作栏
        Divider(parent).pack(fill="x", padx=12, pady=4)
        ctrl = tk.Frame(parent, bg=C["bg"])
        ctrl.pack(fill="x", padx=12, pady=8)

        # 变量替换输入
        var_row = tk.Frame(ctrl, bg=C["bg"])
        var_row.pack(fill="x", pady=(0, 6))
        tk.Label(var_row, text="变量替换 key=value，用逗号分隔：",
                 bg=C["bg"], fg=C["text2"], font=FONT_SMALL).pack(side="left")
        self._batch_var_entry = tk.Entry(
            var_row, bg=C["surface3"], fg=C["text"],
            insertbackground=C["text"], relief=tk.FLAT, font=FONT_UI,
            highlightthickness=1, highlightbackground=C["border"],
            highlightcolor=C["accent"], width=30
        )
        self._batch_var_entry.insert(0, "name=张三,date=今天")
        self._batch_var_entry.pack(side="left", padx=8)

        # 执行按钮行
        exec_row = tk.Frame(ctrl, bg=C["bg"])
        exec_row.pack(fill="x")

        self._batch_status_lbl = tk.Label(
            exec_row, text="就绪", bg=C["bg"], fg=C["text3"], font=FONT_SMALL
        )
        self._batch_status_lbl.pack(side="left")

        FlatButton(exec_row, "▶  立即执行", command=self._batch_run,
                   style="success", width=120, height=34).pack(side="right", padx=(8, 0))
        FlatButton(exec_row, "👁  预览", command=self._batch_dry_run,
                   style="default", width=80, height=34).pack(side="right", padx=(8, 0))

        self._batch_tasks: list = []
        self._batch_file: "Path | None" = None

    def _batch_gen_template(self):
        from tkinter import filedialog
        from pathlib import Path
        from .batch import create_template

        out = filedialog.asksaveasfilename(
            title="保存模版到",
            defaultextension=".xlsx",
            filetypes=[("Excel 文件", "*.xlsx")],
            initialfile="weme_batch_template.xlsx",
        )
        if not out:
            return
        try:
            create_template(Path(out))
            self._batch_status_lbl.configure(
                text=f"✅ 模版已生成：{Path(out).name}", fg=C["green"]
            )
            self._log(f"模版生成: {out}")
        except Exception as exc:
            self._batch_status_lbl.configure(text=f"❌ {exc}", fg=C["red"])

    def _batch_import(self):
        from tkinter import filedialog
        from pathlib import Path
        from .batch import parse_excel

        path = filedialog.askopenfilename(
            title="选择任务 Excel",
            filetypes=[("Excel 文件", "*.xlsx *.xls")],
        )
        if not path:
            return
        try:
            tasks = parse_excel(Path(path))
            self._batch_tasks = tasks
            self._batch_file = Path(path)
            self._batch_path_var.set(f"📄 {Path(path).name}  ({len(tasks)} 条任务)")
            self._refresh_batch_tree(tasks)
            self._batch_status_lbl.configure(
                text=f"已加载 {len(tasks)} 条任务", fg=C["text2"]
            )
            self._log(f"批量任务已导入: {Path(path).name}")
        except Exception as exc:
            self._batch_status_lbl.configure(text=f"❌ 解析失败: {exc}", fg=C["red"])

    def _refresh_batch_tree(self, tasks):
        self._batch_tree.delete(*self._batch_tree.get_children())
        STATUS_TAGS = {
            "已完成": "done", "失败": "fail",
            "发送中": "running", "已计划": "scheduled",
        }
        self._batch_tree.tag_configure("done",      background=C["green_dim"],   foreground=C["green"])
        self._batch_tree.tag_configure("fail",      background=C["red_dim"],     foreground=C["red"])
        self._batch_tree.tag_configure("running",   background=C["accent_dim"],  foreground=C["white"])
        self._batch_tree.tag_configure("scheduled", background=C["surface3"],    foreground=C["yellow"])

        for t in tasks:
            send_at = t.send_at.strftime("%m-%d %H:%M") if t.send_at else "立即"
            preview = (t.text[:30] + "…") if len(t.text) > 30 else t.text
            app_icon = {"wechat": "💬", "dingtalk": "📌", "feishu": "🪶"}.get(t.app.value, "")
            tag = STATUS_TAGS.get(t.status.value, "")
            self._batch_tree.insert("", "end", iid=str(t.row_num), tags=(tag,), values=(
                f"{app_icon} {t.app.value}",
                t.target,
                t.msg_type.value,
                preview,
                send_at,
                t.repeat or "单次",
                t.status.value,
            ))

    def _parse_batch_vars(self) -> dict[str, str]:
        raw = self._batch_var_entry.get().strip()
        result: dict[str, str] = {}
        for pair in raw.split(","):
            pair = pair.strip()
            if "=" in pair:
                k, _, v = pair.partition("=")
                result[k.strip()] = v.strip()
        return result

    def _batch_dry_run(self):
        if not self._batch_tasks:
            self._batch_status_lbl.configure(text="⚠ 先导入任务表格", fg=C["yellow"])
            return
        self._refresh_batch_tree(self._batch_tasks)
        self._batch_status_lbl.configure(
            text=f"预览: {len(self._batch_tasks)} 条任务（未发送）", fg=C["text2"]
        )

    def _batch_run(self):
        if not self._batch_tasks:
            self._batch_status_lbl.configure(text="⚠ 先导入任务表格", fg=C["yellow"])
            return

        from .batch import TaskStatus
        from .sender import BatchScheduler

        variables = self._parse_batch_vars()
        self._batch_status_lbl.configure(text="⏳ 正在执行...", fg=C["yellow"])

        def on_update(task):
            # 更新 tree 中对应行
            try:
                send_at = task.send_at.strftime("%m-%d %H:%M") if task.send_at else "立即"
                preview = (task.text[:30] + "…") if len(task.text) > 30 else task.text
                app_icon = {"wechat": "💬", "dingtalk": "📌", "feishu": "🪶"}.get(task.app.value, "")
                STATUS_TAGS = {
                    "已完成": "done", "失败": "fail",
                    "发送中": "running", "已计划": "scheduled",
                }
                tag = STATUS_TAGS.get(task.status.value, "")
                iid = str(task.row_num)
                if self._batch_tree.exists(iid):
                    self._batch_tree.item(iid, tags=(tag,), values=(
                        f"{app_icon} {task.app.value}", task.target,
                        task.msg_type.value, preview, send_at,
                        task.repeat or "单次", task.status.value,
                    ))
            except Exception:
                pass
            self._log(f"[批量] 行{task.row_num} {task.target}: {task.status.value}")

        def run_thread():
            scheduler = BatchScheduler(
                tasks=self._batch_tasks,
                excel_path=self._batch_file,
                on_update=on_update,
                variables=variables,
                interval_secs=2.0,
            )
            scheduler.start()
            scheduler.wait(timeout=3600)
            summary = scheduler.summary
            done = summary.get("已完成", 0)
            fail = summary.get("失败", 0)
            self.reply_queue.put(("status",
                f"批量完成: ✓{done} ✗{fail} / {len(self._batch_tasks)}", None))

        threading.Thread(target=run_thread, daemon=True).start()

    def _build_right_panel(self, parent):
        rp = tk.Frame(parent, bg=C["surface"], width=310)
        rp.pack(side="right", fill="y")
        rp.pack_propagate(False)

        # AI 建议
        hdr = tk.Frame(rp, bg=C["surface"])
        hdr.pack(fill="x", padx=14, pady=(16, 4))
        tk.Label(hdr, text="✨  AI 建议", font=FONT_TITLE,
                 bg=C["surface"], fg=C["text"]).pack(side="left")
        self._risk_lbl = tk.Label(hdr, text="●  就绪", bg=C["surface"],
                                   fg=C["text3"], font=FONT_TAG)
        self._risk_lbl.pack(side="right")

        # 建议文本区
        sug_wrap = tk.Frame(rp, bg=C["surface3"], padx=1, pady=1)
        sug_wrap.pack(fill="x", padx=14, pady=4)
        self._sug_text = tk.Text(
            sug_wrap, height=7, bg=C["surface2"], fg=C["text"],
            insertbackground=C["text"], relief=tk.FLAT, font=FONT_UI,
            wrap="word", padx=10, pady=8
        )
        self._sug_text.pack(fill="x")
        self._sug_text.insert("1.0", "等待消息中...")
        self._sug_text.configure(state="disabled")

        # 按钮
        btns = tk.Frame(rp, bg=C["surface"])
        btns.pack(fill="x", padx=14, pady=6)
        FlatButton(btns, "✓  Approve & Send",
                   command=self._approve, style="success",
                   width=176, height=36).pack(side="left")
        FlatButton(btns, "✗  Reject",
                   command=self._reject, style="danger",
                   width=96, height=36).pack(side="right")

        Divider(rp).pack(fill="x", padx=14, pady=10)

        # 风控信息
        self._risk_frame = tk.Frame(rp, bg=C["surface"])
        self._risk_frame.pack(fill="x", padx=14)
        self._risk_detail = tk.Label(
            self._risk_frame, text="", bg=C["surface"],
            fg=C["yellow"], font=FONT_SMALL, wraplength=270, justify="left"
        )
        self._risk_detail.pack(anchor="w")

        Divider(rp).pack(fill="x", padx=14, pady=10)

        # Provider 状态
        prov_row = tk.Frame(rp, bg=C["surface"])
        prov_row.pack(fill="x", padx=14)
        tk.Label(prov_row, text="Provider:", bg=C["surface"],
                 fg=C["text3"], font=FONT_TAG).pack(side="left")
        self._prov_lbl = tk.Label(prov_row, text=self.config.provider,
                                   bg=C["surface"], fg=C["accent"], font=FONT_TAG)
        self._prov_lbl.pack(side="left", padx=6)

        FlatButton(rp, "⚙  配置大模型",
                   command=self._open_config, style="primary",
                   width=282, height=34).pack(padx=14, pady=8)

        Divider(rp).pack(fill="x", padx=14, pady=8)

        # 日志
        tk.Label(rp, text="运行日志", bg=C["surface"],
                 fg=C["text2"], font=FONT_SMALL, padx=14, anchor="w").pack(fill="x")

        self._log_text = tk.Text(
            rp, height=8, bg=C["bg"], fg=C["text3"],
            relief=tk.FLAT, font=FONT_MONO, wrap="word",
            padx=8, pady=6, state="disabled"
        )
        self._log_text.pack(fill="both", expand=True, padx=14, pady=(4, 14))

    def _build_statusbar(self):
        self._status_bar = tk.Label(
            self.root, text="就绪", font=FONT_TAG,
            bg=C["surface2"], fg=C["text3"],
            anchor="w", padx=12, pady=4
        )
        self._status_bar.pack(side="bottom", fill="x")

    # ── Interactions ──────────────────────────────────────────────────────

    def _switch_app(self, app_key: AppKind):
        self.current_app = app_key
        meta = APP_META[app_key]
        self._sb_select(app_key)
        self._hdr_icon.configure(text=meta["icon"])
        self._hdr_title.configure(text=meta["label"])
        self._log(f"切换到 {meta['label']}")
        self._set_status(f"已切换到 {meta['label']}")
        if self._watching:
            self._stop_daemon()
            self._start_daemon()

    def _open_chat_from_search(self):
        """搜索框按 Enter：打开指定联系人/群聊"""
        name = self._search_var.get().strip()
        if not name:
            return
        meta = APP_META[self.current_app]
        self._set_status(f"正在 {meta['label']} 中搜索「{name}」...")
        self._log(f"搜索: {name}（{meta['label']}）")

        def _do():
            from .apps.registry import get_app_adapter
            adapter = get_app_adapter(self.current_app)
            ok = adapter.open_chat(name)
            if ok:
                self.reply_queue.put(("status", f"✓ 已打开「{name}」", None))
            else:
                self.reply_queue.put(("status", f"⚠ 未能确认打开「{name}」（需辅助功能权限）", None))

        threading.Thread(target=_do, daemon=True).start()
        self._search_var.set("")  # 清空输入框

    def _toggle_watch(self):
        if self._watching:
            self._stop_daemon()
            self._watching = False
            self._draw_watch_btn()
            self._hdr_sub.configure(text="已停止", fg=C["text3"])
            self._set_status("已停止监听")
        else:
            self._start_daemon()
            self._watching = True
            self._draw_watch_btn()
            meta = APP_META[self.current_app]
            self._hdr_sub.configure(text="监听中...", fg=C["green"])
            self._set_status(f"正在监听 {meta['label']}（{self.config.provider}）")

    def _start_daemon(self):
        self.stop_event.clear()
        self.config.default_mode = self._mode_var.get()
        try:
            self.daemon = AutoReplyDaemon(
                self.current_app, self.config,
                auto_send=False,
                data_store=self.data_store,
            )
        except Exception as exc:
            self._log(f"⚠ 初始化失败: {exc}")
            return

        def _run():
            while not self.stop_event.is_set():
                try:
                    reply = self.daemon.step()
                    if reply:
                        self.reply_queue.put(("suggestion", reply, self.daemon))
                except Exception as exc:
                    self.reply_queue.put(("error", str(exc), None))
                self.stop_event.wait(self.config.poll_interval)

        self.daemon_thread = threading.Thread(target=_run, daemon=True)
        self.daemon_thread.start()

    def _stop_daemon(self):
        self.stop_event.set()
        if self.daemon_thread:
            self.daemon_thread.join(timeout=5)
            self.daemon_thread = None

    def _poll_queue(self):
        try:
            while True:
                item = self.reply_queue.get_nowait()
                kind = item[0]
                if kind == "suggestion":
                    _, text, daemon = item
                    self._show_suggestion(text, daemon)
                elif kind == "error":
                    _, msg, _ = item
                    self._log(f"⚠ {msg}")
                elif kind == "status":
                    _, msg, _ = item
                    self._set_status(msg)
                    self._log(msg)
        except:
            pass
        self.root.after(500, self._poll_queue)

    def _show_suggestion(self, text: str, daemon):
        self._current_suggestion = text
        self._current_daemon = daemon
        self._sug_text.configure(state="normal")
        self._sug_text.delete("1.0", "end")
        self._sug_text.insert("1.0", text)
        self._sug_text.configure(state="disabled")
        self._risk_lbl.configure(text="● 待审核", fg=C["yellow"])
        self._add_msg(f"[AI 建议] {text}", "ai")
        self._log(f"新建议: {text[:50]}...")
        self._set_status("收到 AI 建议，请审核")

    def _approve(self):
        text = self._current_suggestion
        if not text or text == "等待消息中...":
            return
        daemon = getattr(self, "_current_daemon", None) or self.daemon
        try:
            if daemon:
                daemon.adapter.send_text(text, press_enter=True)
            self._add_msg(f"[已发送] {text}", "sent")
            self._log("✓ 已批准并发送")
            self._set_status("消息已发送")
            self._clear_suggestion()
        except Exception as exc:
            messagebox.showerror("发送失败", str(exc))

    def _reject(self):
        self._log("✗ 建议已拒绝")
        self._set_status("建议已拒绝")
        self._clear_suggestion()

    def _clear_suggestion(self):
        self._current_suggestion = ""
        self._sug_text.configure(state="normal")
        self._sug_text.delete("1.0", "end")
        self._sug_text.insert("1.0", "等待下一条消息...")
        self._sug_text.configure(state="disabled")
        self._risk_lbl.configure(text="● 就绪", fg=C["text3"])
        self._risk_detail.configure(text="")

    def _on_mode_change(self):
        mode = self._mode_var.get()
        self.config.default_mode = mode
        if self.daemon:
            self.daemon.mode = mode
        self._log(f"模式: {mode}")

    def _open_config(self):
        def on_save(cfg):
            self.config = cfg
            self._prov_lbl.configure(text=cfg.provider)
            self._log(f"配置已更新: {cfg.provider} / {cfg.model or '默认模型'}")
            self._set_status(f"Provider: {cfg.provider}")
            if self._watching:
                self._stop_daemon()
                self._watching = False
                self._draw_watch_btn()
                self._hdr_sub.configure(text="配置已更新，重新监听", fg=C["yellow"])
        ConfigDialog(self.root, self.config, on_save)

    # ── Messages ──────────────────────────────────────────────────────────

    def _add_msg(self, text: str, role: str = "user"):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M")

        row = tk.Frame(self._msg_inner, bg=C["bg"])
        row.pack(fill="x", padx=12, pady=3)

        if role == "system":
            tk.Label(row, text=text, bg=C["bg"], fg=C["text3"],
                     font=FONT_TAG, justify="center").pack()
        elif role in ("ai", "suggestion"):
            left = tk.Frame(row, bg=C["bg"])
            left.pack(side="left")
            tk.Label(left, text="🤖", font=("Helvetica", 14),
                     bg=C["bg"]).pack(anchor="w")
            bubble = tk.Frame(left, bg=C["surface3"], padx=10, pady=6)
            bubble.pack(anchor="w")
            tk.Label(bubble, text=text, bg=C["surface3"], fg=C["text"],
                     font=FONT_UI, wraplength=340, justify="left").pack(anchor="w")
            tk.Label(left, text=ts, bg=C["bg"], fg=C["text3"],
                     font=FONT_TAG).pack(anchor="w")
        elif role == "sent":
            right = tk.Frame(row, bg=C["bg"])
            right.pack(side="right")
            bubble = tk.Frame(right, bg=C["accent_dim"], padx=10, pady=6)
            bubble.pack(anchor="e")
            tk.Label(bubble, text=text.replace("[已发送] ", ""),
                     bg=C["accent_dim"], fg=C["white"],
                     font=FONT_UI, wraplength=300, justify="right").pack()
            tk.Label(right, text=f"✓ {ts}", bg=C["bg"], fg=C["green"],
                     font=FONT_TAG).pack(anchor="e")
        else:
            right = tk.Frame(row, bg=C["bg"])
            right.pack(side="right")
            bubble = tk.Frame(right, bg=C["surface2"], padx=10, pady=6)
            bubble.pack(anchor="e")
            tk.Label(bubble, text=text, bg=C["surface2"], fg=C["text"],
                     font=FONT_UI, wraplength=320, justify="right").pack()
            tk.Label(right, text=ts, bg=C["bg"], fg=C["text3"],
                     font=FONT_TAG).pack(anchor="e")

        # 滚动到底
        self._msg_canvas.update_idletasks()
        self._msg_canvas.yview_moveto(1.0)

    def _log(self, msg: str):
        from datetime import datetime
        ts = datetime.now().strftime("%H:%M:%S")
        self._log_text.configure(state="normal")
        self._log_text.insert("end", f"[{ts}] {msg}\n")
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _set_status(self, msg: str):
        self._status_bar.configure(text=msg)

    def _on_close(self):
        self._stop_daemon()
        if self.data_store:
            self.data_store.close()
        self.root.destroy()

    def run(self):
        self._log("Weme 虾说已启动")
        self._log(f"Provider: {self.config.provider}  |  模式: {self.config.default_mode}")
        self.root.mainloop()


def launch_dashboard(config: AssistantConfig) -> None:
    WemeDashboard(config).run()
