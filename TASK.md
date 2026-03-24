# Build Task: Weme v2 - 虾说桌面聊天助手

## 背景

参考原项目 https://github.com/howtimeschange/weme 完成 v2 重构。
v2 的核心升级：**接替人工**处理微信/钉钉/飞书消息，双端支持 macOS + Windows。

## 核心要求

### 1. 平台适配层 (platform/)

原项目只支持 macOS AppleScript/Accessibility，v2 需要统一抽象：

```
platform/
  base.py          # 抽象基类 PlatformAutomation
  macos.py         # macOS: AppleScript + pyobjc/Accessibility
  windows.py       # Windows: pywin32 + UIAutomation (comtypes/uiautomation)
  factory.py       # 自动检测 sys.platform 返回正确实现
```

**macOS 实现：**
- `activate_app(app_name)` → `subprocess.run(["open", "-a", app_name])`
- `read_accessibility(process_name)` → osascript dump AXStaticText/AXTextArea
- `write_clipboard(text)` → pbcopy
- `paste_and_send()` → pyautogui Cmd+V + Enter

**Windows 实现：**
- `activate_app(app_name)` → `win32gui.FindWindow` + `SetForegroundWindow`
- `read_accessibility(process_name)` → `uiautomation` 库遍历 UI tree
- `write_clipboard(text)` → `pyperclip` 或 `win32clipboard`
- `paste_and_send()` → `pyautogui` Ctrl+V + Enter

### 2. 应用适配层 (apps/)

保留原来的逻辑，但基于新 platform 层：

```
apps/
  base.py          # AppAdapter 抽象类，统一接口
  wechat.py        # 微信适配
  dingtalk.py      # 钉钉适配（含工作时段/白名单）
  feishu.py        # 飞书/Lark 适配
  registry.py      # APP_ADAPTERS 注册表
```

每个 adapter 必须实现：
- `activate()` → 激活窗口
- `read_snapshot()` → AppSnapshot
- `send_text(text, press_enter=True)` → 发送消息
- `pick_latest_message(snapshot)` → 最新一条消息

### 3. 核心数据模型 (core/types.py)

```python
@dataclass
class AppSnapshot:
    app_name: str
    window_title: str
    raw_text: str
    message_lines: tuple[str, ...]

@dataclass
class ChatTurn:
    role: str   # "user" | "assistant"
    content: str

@dataclass
class MemoryContext:
    user_profile_text: str
    contact_card_text: str
    recent_summary_text: str
    raw_evidence: tuple
    sources: tuple[str, ...]

@dataclass
class ReplyRequest:
    contact_name: str
    contact_id: str
    chat_id: str
    latest_inbound: str
    conversation: tuple[ChatTurn, ...]
    workspace_root: Path
    profile: str
    max_reply_chars: int
    source_app: str
    window_title: str
    mode: str
    memory: MemoryContext | None = None
    knowledge_context: tuple = ()
```

### 4. 记忆系统 (memory/)

分层记忆，L0-L4：
```
memory/
  engine.py        # MemoryEngine 主类
  layers.py        # L0-L4 各层读写
  summarizer.py    # 会话摘要生成
```

### 5. LLM Provider 网关 (providers/)

```
providers/
  base.py          # ReplyProvider 抽象 + LLMResponse dataclass
  mock.py          # 本地测试
  openai_compat.py # DeepSeek/MiniMax/OpenAI-compatible
  anthropic.py     # Claude
  router.py        # 路由 + fallback 逻辑
```

### 6. 风控引擎 (risk.py)

- 三级风险：low / medium / high
- 高风险关键词：金额、转账、借贷、法律、医疗、"保证"/"一定"/"承诺"
- 熔断：连续失败≥3暂停，连续高风险≥5进入人工模式

### 7. 主循环 Daemon (daemon.py)

- 轮询间隔可配置（默认 3s）
- snapshot hash 去重避免重复触发
- 支持 suggest / auto / hybrid 三种模式
- 写 SQLite 审计记录

### 8. SQLite 存储 (store.py)

三张核心表：
- `conversations` (id, app_key, chat_id, title, ...)
- `messages` (id, conversation_id, role, content, ...)
- `suggestions` (id, conversation_id, reply_text, risk_level, decision, status, ...)

### 9. 桌面 UI (dashboard.py)

三栏式 Tkinter 工作台：
- 左栏：应用切换（微信/钉钉/飞书）+ 运行状态指示
- 中栏：会话列表 + 当前对话消息流
- 右栏：AI 建议卡片（含 Approve/Reject 按钮）+ 风控提示 + 配置面板

UI 要求：
- 用 ttk 主题（azure 或 clam），不用原生灰色
- 建议卡片有明显的绿色 "✓ Approve & Send" 按钮
- 高风险建议显示红色警告框
- 实时日志面板（底部可折叠）

### 10. CLI 入口 (cli.py)

用 typer 实现：
```
weme gui           # 打开 GUI
weme watch         # 后台监听
weme reply "消息"  # 单次回复测试
weme inspect       # 读取当前窗口快照（调试用）
weme send "文本"   # 直接发到当前激活窗口
weme bootstrap     # 历史回灌
```

### 11. 配置 (config/)

```
config/
  app.yaml          # provider/mode/timeout 等
  providers.yaml    # 各 LLM provider 配置
  rules.yaml        # 白黑名单/活跃时段/敏感词
  prompts/
    system.md
    reply.md
    summarize.md
```

### 12. 打包

```
scripts/
  build_macos_app.py   # PyInstaller → .app
  build_windows_exe.py # PyInstaller → .exe
```

`pyproject.toml` 依赖：
- 核心: `typer`, `pyyaml`, `httpx`, `sqlalchemy`
- macOS: `pyobjc-framework-Cocoa`, `pyautogui`
- Windows: `pywin32`, `comtypes`, `pyperclip`, `pyautogui`
- 可选: `openai`, `anthropic`

## 目录结构

```
weme-v2/
├── README.md
├── SPEC.md              (从原项目复制/更新)
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
│   ├── app.yaml
│   ├── providers.yaml
│   ├── rules.yaml
│   └── prompts/
│       ├── system.md
│       ├── reply.md
│       └── summarize.md
├── profiles/
│   ├── USER.md
│   └── contacts/
├── memory/
│   ├── summaries/
│   ├── raw/
│   ├── checkpoints/
│   └── exports/
├── src/
│   └── weme/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── daemon.py
│       ├── dashboard.py
│       ├── store.py
│       ├── risk.py
│       ├── audit.py
│       ├── prompt.py
│       ├── config.py
│       ├── workspace.py
│       ├── defaults.py
│       ├── state.py
│       ├── work_mode.py
│       ├── knowledge.py
│       ├── clipboard.py
│       ├── core/
│       │   └── types.py
│       ├── platform/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── macos.py
│       │   ├── windows.py
│       │   └── factory.py
│       ├── apps/
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── wechat.py
│       │   ├── dingtalk.py
│       │   ├── feishu.py
│       │   └── registry.py
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── engine.py
│       │   ├── layers.py
│       │   └── summarizer.py
│       └── providers/
│           ├── __init__.py
│           ├── base.py
│           ├── mock.py
│           ├── openai_compat.py
│           ├── anthropic.py
│           └── router.py
├── scripts/
│   ├── build_macos_app.py
│   └── build_windows_exe.py
└── tests/
    ├── unit/
    └── integration/
```

## 关键设计决策

1. **platform 层完全隔离 OS 差异**：apps 层只调用 `platform.activate_app()` 等通用接口，不关心底层 OS 实现。
2. **Windows accessibility 用 `uiautomation` 库**：比 pywin32 直接操作 HWND 更可靠，支持 UIA 标准。
3. **macOS 优先，Windows 尽力而为**：Windows 因各应用 UI 自动化支持差异大，用 best-effort 原则。
4. **GUI 用 Tkinter + ttk**：不引入重依赖（Qt/Electron），保持轻量，打包简单。
5. **SQLite 不用 ORM**：直接用 sqlite3，减少依赖，兼容性好。

## 完成后

所有代码写好后：
1. `git add -A && git commit -m "feat: initial weme v2 implementation" && git push`
2. 运行 `python3 -m py_compile` 验证所有 Python 文件语法正确
3. 确保 `python3 -c "from src.weme.cli import app"` 不报错

完成后运行: openclaw system event --text "Done: weme-v2 全部代码已完成，覆盖 platform/apps/providers/daemon/dashboard/cli，已 push 到 GitHub" --mode now
