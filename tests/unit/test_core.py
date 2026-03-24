"""Unit tests for weme v2"""
import sys
import pytest
from pathlib import Path

# 确保 src 在 path 里
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_types_import() -> None:
    from weme.core.types import AppSnapshot, ChatTurn, MemoryContext, ReplyRequest, LLMResponse
    snapshot = AppSnapshot(app_name="wechat", window_title="张三", raw_text="hello", message_lines=("hello",))
    assert snapshot.app_name == "wechat"


def test_risk_assessment() -> None:
    from weme.core.types import ReplyRequest, MemoryContext
    from weme.risk import assess_risk, decide_action

    request = ReplyRequest(
        contact_name="test",
        contact_id="test",
        chat_id="test",
        latest_inbound="你好",
        conversation=(),
        workspace_root=Path("/tmp"),
        profile="",
        max_reply_chars=120,
        source_app="wechat",
        window_title="test",
        mode="hybrid",
    )

    # 低风险回复
    assessment = assess_risk(request, "好的，稍等。")
    assert assessment.level == "low"

    # 高风险回复
    assessment = assess_risk(request, "我保证会给你转账的。")
    assert assessment.level == "high"


def test_risk_decide_action() -> None:
    from weme.risk import assess_risk, decide_action, RiskAssessment
    from weme.core.types import ReplyRequest
    from pathlib import Path

    request = ReplyRequest(
        contact_name="test",
        contact_id="test",
        chat_id="test",
        latest_inbound="你好",
        conversation=(),
        workspace_root=Path("/tmp"),
        profile="",
        max_reply_chars=120,
        source_app="wechat",
        window_title="test",
        mode="suggest",
    )

    low_risk = RiskAssessment(level="low", reasons=(), score=0)
    decision = decide_action("suggest", low_risk)
    assert decision.action == "confirm"

    decision = decide_action("auto", low_risk)
    assert decision.action == "auto_send"

    decision = decide_action("hybrid", low_risk)
    assert decision.action == "auto_send"

    high_risk = RiskAssessment(level="high", reasons=("高风险词",), score=50)
    decision = decide_action("hybrid", high_risk)
    assert decision.action == "block"


def test_mock_provider() -> None:
    from weme.core.types import ReplyRequest, MemoryContext
    from weme.providers.mock import MockReplyProvider

    provider = MockReplyProvider()
    request = ReplyRequest(
        contact_name="test",
        contact_id="test",
        chat_id="test",
        latest_inbound="你好",
        conversation=(),
        workspace_root=Path("/tmp"),
        profile="",
        max_reply_chars=120,
        source_app="wechat",
        window_title="test",
        mode="hybrid",
    )
    reply = provider.generate(request)
    assert reply
    assert "[mock]" in reply


def test_state_store() -> None:
    from weme.state import StateStore, ConversationState
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        tmp = Path(f.name)

    try:
        store = StateStore(tmp)
        state = ConversationState(snapshot_hash="abc", last_sent_text="hello")
        store.save("key1", state)

        loaded = store.load("key1")
        assert loaded.snapshot_hash == "abc"
        assert loaded.last_sent_text == "hello"

        # 新 key 返回默认值
        default = store.load("nonexistent")
        assert default.snapshot_hash == ""
    finally:
        os.unlink(tmp)


def test_store_db() -> None:
    from weme.store import AppDataStore
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        tmp = Path(f.name)

    try:
        store = AppDataStore(tmp)
        msg_id = store.record_message(
            app_key="wechat",
            chat_id="conv1",
            title="张三",
            contact_name="张三",
            content="你好",
            role="user",
            direction="incoming",
            source_key="test:1",
        )
        assert msg_id > 0

        sugg_id = store.record_suggestion(
            app_key="wechat",
            chat_id="conv1",
            title="张三",
            contact_name="张三",
            reply_text="好的",
            source_key="test:suggest:1",
        )
        assert sugg_id > 0

        store.update_suggestion_status(sugg_id, status="published")
        store.close()
    finally:
        os.unlink(tmp)


def test_work_mode_policy() -> None:
    from weme.work_mode import DingTalkWorkModePolicy
    from weme.core.types import ReplyRequest

    policy = DingTalkWorkModePolicy(enabled=False)
    request = ReplyRequest(
        contact_name="张三",
        contact_id="张三",
        chat_id="test",
        latest_inbound="你好",
        conversation=(),
        workspace_root=Path("/tmp"),
        profile="",
        max_reply_chars=120,
        source_app="dingtalk",
        window_title="张三",
        mode="hybrid",
    )
    # 未启用时无限制
    assert policy.allows_auto_send(request) is True

    policy_with_whitelist = DingTalkWorkModePolicy(
        enabled=True,
        whitelist_contacts=("张三", "李四"),
        work_hours_start=0,
        work_hours_end=24,
    )
    assert policy_with_whitelist.allows_auto_send(request) is True

    policy_strict = DingTalkWorkModePolicy(
        enabled=True,
        whitelist_contacts=("李四",),  # 不包含张三
        work_hours_start=0,
        work_hours_end=24,
    )
    assert policy_strict.allows_auto_send(request) is False
