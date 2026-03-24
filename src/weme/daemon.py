from __future__ import annotations

import hashlib
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from .apps.registry import get_app_adapter
from .audit import AuditLogger
from .config import AssistantConfig
from .core.types import AppKind, AppSnapshot, ChatTurn, ReplyRequest, MemoryContext
from .memory import MemoryEngine
from .providers.router import build_provider
from .risk import assess_risk, decide_action
from .state import ConversationState, StateStore
from .store import AppDataStore
from .workspace import workspace_paths
from .work_mode import DingTalkWorkModePolicy


def _snapshot_hash(snapshot: AppSnapshot) -> str:
    payload = "\n".join([
        snapshot.app_name,
        snapshot.window_title,
        *snapshot.message_lines[-30:],
    ])
    return hashlib.sha256(payload.encode("utf-8", errors="ignore")).hexdigest()


def _turns_from_lines(
    lines: tuple[str, ...],
    last_sent_text: str = "",
) -> tuple[ChatTurn, ...]:
    turns: list[ChatTurn] = []
    for line in lines:
        role = (
            "assistant"
            if last_sent_text and line.strip() == last_sent_text.strip()
            else "user"
        )
        turns.append(ChatTurn(role=role, content=line.strip()))
    return tuple(turns)


class AutoReplyDaemon:
    """自动回复主循环：监听 → 记忆 → 生成 → 风控 → 发送"""

    def __init__(
        self,
        app: AppKind,
        config: AssistantConfig,
        *,
        auto_send: bool = False,
        state_store: StateStore | None = None,
        data_store: AppDataStore | None = None,
    ) -> None:
        self.app = app
        self.config = config
        self.auto_send = auto_send

        self.adapter = get_app_adapter(app)
        self.provider = build_provider(
            config.provider,
            model=config.model,
            api_key=config.api_key,
            base_url=config.base_url,
            temperature=config.temperature,
            timeout_ms=config.timeout_ms,
            fallback_provider=config.fallback_provider,
            fallback_model=config.fallback_model,
            fallback_api_key=config.fallback_api_key,
            fallback_base_url=config.fallback_base_url,
        )

        ws = workspace_paths(config.workspace_root)
        ws.ensure()

        self.state_store = state_store or StateStore(ws.data_dir / "state.json")
        self.data_store = data_store or AppDataStore(ws.data_dir / "app.db")
        self.memory_engine = MemoryEngine(ws)
        self.audit_logger = AuditLogger(ws.logs_dir)
        self.work_policy = DingTalkWorkModePolicy(
            enabled=config.dingtalk_work_mode and app == "dingtalk",
            whitelist_contacts=config.dingtalk_whitelist,
        )
        self.mode = config.default_mode

    def _paused_until(self, value: str) -> bool:
        if not value:
            return False
        try:
            until = datetime.fromisoformat(value)
        except ValueError:
            return False
        return until > datetime.now(timezone.utc)

    def _set_pause(self, state: ConversationState, hours: int) -> ConversationState:
        paused = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
        return ConversationState(
            snapshot_hash=state.snapshot_hash,
            last_sent_text=state.last_sent_text,
            last_window_title=state.last_window_title,
            send_failure_count=state.send_failure_count,
            high_risk_count=state.high_risk_count,
            paused_until=paused,
        )

    def step(self) -> str | None:
        """执行一次检查-生成-发送循环，返回建议文本或 None"""
        snapshot = self.adapter.read_snapshot()
        if not snapshot.raw_text and not snapshot.message_lines:
            return None

        state_key = f"{self.app}:{snapshot.window_title or self.adapter.app_names[0]}"
        state = self.state_store.load(state_key)

        if self._paused_until(state.paused_until):
            return None

        current_hash = _snapshot_hash(snapshot)
        if state.snapshot_hash == current_hash:
            return None

        latest_inbound = self.adapter.pick_latest_message(snapshot)
        if not latest_inbound:
            return None

        chat_title = snapshot.window_title or latest_inbound[:24] or snapshot.app_name
        chat_id = snapshot.window_title or latest_inbound[:64] or snapshot.app_name

        # 记录入站消息
        incoming_id = self.data_store.record_message(
            app_key=self.app,
            chat_id=chat_id,
            title=chat_title,
            contact_name=chat_title,
            content=latest_inbound,
            role="user",
            direction="incoming",
            sender_name=chat_title,
            origin_app=snapshot.app_name,
            source_key=f"{current_hash}:incoming",
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        # 构建请求
        message_lines = snapshot.message_lines
        prior_lines = message_lines[:-1] if len(message_lines) > 1 else ()

        # Prefer structured history from snapshot (speaker-attributed ChatTurns).
        # Fall back to heuristic line-based parsing when history is empty.
        if snapshot.history:
            # Exclude the very last turn if it's the latest_inbound (avoid duplication)
            history_turns = snapshot.history
            if history_turns and history_turns[-1].content.strip() == latest_inbound.strip():
                history_turns = history_turns[:-1]
            conversation = history_turns[-self.config.history_window:]
        else:
            conversation = _turns_from_lines(
                prior_lines[-self.config.history_window:],
                last_sent_text=state.last_sent_text,
            )

        request = ReplyRequest(
            contact_name=chat_title,
            contact_id=chat_title,
            chat_id=chat_id,
            latest_inbound=latest_inbound,
            conversation=conversation,
            workspace_root=self.config.workspace_root,
            profile=self.config.profile,
            max_reply_chars=self.config.max_reply_chars,
            source_app=snapshot.app_name,
            window_title=snapshot.window_title,
            mode=self.mode,
        )

        # 记忆检索
        memory_context = self.memory_engine.build_memory_context(request)
        request = replace(request, memory=memory_context)

        # 写入原始记录
        self.memory_engine.append_raw_message(
            contact_name=chat_title,
            content=latest_inbound,
            role="user",
        )

        # 生成回复
        try:
            reply = self.provider.generate(request).strip()
        except Exception as exc:
            self.audit_logger.log_event("generate_error", {"error": str(exc), "chat_id": chat_id})
            return None

        if not reply:
            return None
        if len(reply) > request.max_reply_chars:
            reply = reply[:request.max_reply_chars].rstrip()

        # 风控评估
        assessment = assess_risk(request, reply)
        decision = decide_action(request.mode, assessment)

        # 记录建议
        suggestion_id = self.data_store.record_suggestion(
            app_key=self.app,
            chat_id=chat_id,
            title=chat_title,
            contact_name=chat_title,
            reply_text=reply,
            mode=request.mode,
            risk_level=assessment.level,
            decision=decision.action,
            provider=self.config.provider,
            model=self.config.model,
            source_key=f"{current_hash}:suggestion",
            incoming_message_id=incoming_id,
            evidence=[
                {"source": c.source, "title": c.title, "content": c.content}
                for c in memory_context.raw_evidence
            ],
            memory={
                "user_profile": memory_context.user_profile_text[:200],
                "contact_card": memory_context.contact_card_text[:200],
            },
            status="blocked" if decision.action == "block" else "pending",
        )

        # 审计
        self.audit_logger.log_reply({
            "incoming_message": latest_inbound,
            "contact_name": chat_title,
            "chat_id": chat_id,
            "provider": self.config.provider,
            "model": self.config.model,
            "mode": request.mode,
            "risk_level": assessment.level,
            "risk_reasons": list(assessment.reasons),
            "decision": decision.action,
            "reply_text": reply,
        })

        # 处理高风险 / 需确认
        if decision.action in ("block", "confirm"):
            next_state = ConversationState(
                snapshot_hash=current_hash,
                last_sent_text=state.last_sent_text,
                last_window_title=snapshot.window_title,
                send_failure_count=state.send_failure_count,
                high_risk_count=state.high_risk_count + 1,
                paused_until=state.paused_until,
            )
            if next_state.high_risk_count >= 5:
                next_state = self._set_pause(next_state, hours=8)
            self.state_store.save(state_key, next_state)
            return reply  # 返回建议，等待人工确认

        # 自动发送判断
        policy_ok = self.work_policy.allows_auto_send(request)
        should_send = self.auto_send and decision.action == "auto_send" and policy_ok

        if should_send:
            try:
                self.adapter.send_text(reply, press_enter=True)
                self.memory_engine.append_raw_message(
                    contact_name=chat_title, content=reply, role="assistant"
                )
                self.data_store.record_message(
                    app_key=self.app,
                    chat_id=chat_id,
                    title=chat_title,
                    contact_name=chat_title,
                    content=reply,
                    role="assistant",
                    direction="outgoing",
                    sender_name="我",
                    origin_app=snapshot.app_name,
                    source_key=f"{current_hash}:outgoing",
                    is_ai_generated=True,
                )
                self.data_store.mark_suggestion_published(suggestion_id)
                self.audit_logger.log_event("reply_auto_sent", {
                    "chat_id": chat_id, "contact_name": chat_title, "reply_text": reply
                })
                next_state = ConversationState(
                    snapshot_hash=current_hash,
                    last_sent_text=reply,
                    last_window_title=snapshot.window_title,
                )
                self.state_store.save(state_key, next_state)
                return None  # 已发送，不需要 UI 显示

            except Exception as exc:
                failed_state = ConversationState(
                    snapshot_hash=current_hash,
                    last_sent_text=state.last_sent_text,
                    last_window_title=snapshot.window_title,
                    send_failure_count=state.send_failure_count + 1,
                )
                if failed_state.send_failure_count >= 3:
                    failed_state = self._set_pause(failed_state, hours=2)
                self.state_store.save(state_key, failed_state)
                self.data_store.update_suggestion_status(
                    suggestion_id, status="pending", publish_error=str(exc)
                )
                return reply

        # suggest 模式或策略不允许 → 返回建议等待 UI 处理
        next_state = ConversationState(
            snapshot_hash=current_hash,
            last_sent_text=state.last_sent_text,
            last_window_title=snapshot.window_title,
        )
        self.state_store.save(state_key, next_state)
        return reply

    def run(self, stop_event: threading.Event | None = None) -> None:
        stop_event = stop_event or threading.Event()
        while not stop_event.is_set():
            try:
                self.step()
            except Exception as exc:
                self.audit_logger.log_event("daemon_error", {"error": str(exc)})
            stop_event.wait(self.config.poll_interval)
