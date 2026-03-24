# Weme v2 / 虾说

**接替人工处理微信、钉钉、飞书消息的桌面助手**

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/platform-macOS%20%7C%20Windows-lightgrey)](https://github.com/howtimeschange/weme-v2)

---

## 功能特性

- 🔍 **监听消息**：自动检测微信/钉钉/飞书新消息
- 🤖 **AI 生成回复**：支持 DeepSeek、MiniMax、Claude、自定义 OpenAI-compatible
- 🛡 **风控保护**：高风险内容强制人工审核，不自动发送
- 📋 **三种模式**：`suggest`（只建议）/ `auto`（自动发送）/ `hybrid`（混合）
- 💾 **记忆系统**：用户画像、联系人名片、会话摘要、历史检索
- 🖥 **桌面 GUI**：三栏工作台，Approve/Reject 一键操作
- 🍎🪟 **双端支持**：macOS (AppleScript) + Windows (UIAutomation)
- 📦 **开箱即用**：可打包为独立 .app / .exe，无需用户安装 Python

---

## 快速开始

### 安装

```bash
git clone https://github.com/howtimeschange/weme-v2.git
cd weme-v2
pip install -e ".[macos]"   # macOS
# 或
pip install -e ".[windows]" # Windows
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 或者直接编辑 config/app.yaml
```

### 使用

```bash
# 打开 GUI 工作台
weme gui

# 命令行监听（建议模式，不自动发送）
weme watch wechat

# 监听并自动发送低风险回复
weme watch wechat --auto-send

# 单次回复测试
weme reply "你好，最近怎么样？"

# 查看当前窗口快照（调试）
weme inspect wechat

# 直接发送文本
weme send "收到" --app wechat

# 历史记录回灌
weme bootstrap ./chat_history.txt --contact "张三"
```

---

## 架构

```
消息采集 (apps/)
  └─ platform/           # macOS / Windows 适配层
     ├─ macos.py         # AppleScript + pyautogui
     └─ windows.py       # UIAutomation + pyautogui

记忆系统 (memory/)
  ├─ USER.md             # 用户画像
  ├─ contacts/           # 联系人名片
  └─ summaries/          # 会话摘要

LLM 网关 (providers/)
  ├─ openai_compat.py    # DeepSeek / MiniMax / OpenAI
  ├─ anthropic.py        # Claude
  ├─ mock.py             # 本地测试
  └─ router.py           # 路由 + Fallback

核心流程
  ├─ daemon.py           # 主循环：监听→生成→风控→发送
  ├─ risk.py             # 风险评估（low/medium/high）
  ├─ store.py            # SQLite 审计记录
  └─ dashboard.py        # Tkinter GUI 工作台
```

---

## 支持的 Provider

| Provider | 模型 | 配置方式 |
|---|---|---|
| DeepSeek | deepseek-chat | `DEEPSEEK_API_KEY` |
| MiniMax | MiniMax-M2.5 | `MINIMAX_API_KEY` |
| Anthropic / Claude | claude-sonnet-4 | `ANTHROPIC_API_KEY` |
| 自定义 OpenAI-compatible | 任意 | `WEME_API_KEY` + `WEME_BASE_URL` |
| Mock | - | 无需配置，测试用 |

---

## 回复模式

| 模式 | 说明 |
|---|---|
| `suggest` | 只生成建议，不自动发送，必须人工确认 |
| `auto` | 低风险自动发送，中高风险人工确认 |
| `hybrid` | 默认。低风险自动，中风险确认，高风险拦截 |

---

## 风控

高风险内容（金融、法律、医疗等）**永远不会自动发送**，只进入建议队列等待人工审核。

连续失败 ≥3 次自动暂停；连续高风险 ≥5 次进入纯人工模式。

---

## 许可证

MIT
