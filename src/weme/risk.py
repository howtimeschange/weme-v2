from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .core.types import ReplyRequest, ReplyMode, RiskLevel

# 高风险关键词
HIGH_RISK_KEYWORDS = frozenset({
    "转账", "汇款", "借钱", "借款", "放款", "投资回报", "年化",
    "保证", "一定赚", "必赚", "稳赚", "无风险",
    "身份证", "银行卡号", "密码", "验证码",
    "律师", "法院", "起诉", "诉讼",
    "医生建议", "确诊", "手术", "用药",
    "一定", "肯定", "承诺", "担保",
})

# 中风险关键词
MEDIUM_RISK_KEYWORDS = frozenset({
    "金额", "价格", "费用", "付款", "收款",
    "合同", "协议", "签字",
    "医院", "病情", "诊断",
    "法律", "条款", "规定",
    "紧急", "立刻", "马上",
})

# 强承诺语气
STRONG_COMMITMENT_RE = re.compile(
    r"(保证|一定|肯定|承诺|担保|不会错|没问题|绝对).{0,8}(会|能|做|给|还|赔)",
    re.UNICODE,
)


@dataclass
class RiskAssessment:
    level: str  # "low" | "medium" | "high"
    reasons: tuple[str, ...]
    score: int  # 0-100


@dataclass
class ActionDecision:
    action: str  # "auto_send" | "confirm" | "block"
    reason: str


def assess_risk(request: "ReplyRequest", reply_text: str) -> RiskAssessment:
    """评估回复内容的风险等级"""
    reasons: list[str] = []
    score = 0

    text_lower = reply_text.lower()

    # 检查高风险关键词
    for kw in HIGH_RISK_KEYWORDS:
        if kw in reply_text:
            reasons.append(f"高风险关键词: {kw}")
            score += 30

    # 检查中风险关键词
    for kw in MEDIUM_RISK_KEYWORDS:
        if kw in reply_text:
            reasons.append(f"中风险词: {kw}")
            score += 10

    # 检查强承诺语气
    if STRONG_COMMITMENT_RE.search(reply_text):
        reasons.append("包含强承诺语气")
        score += 25

    # 回复过长可能包含复杂承诺
    if len(reply_text) > request.max_reply_chars * 1.5:
        reasons.append("回复内容过长")
        score += 10

    # 综合判断等级
    if score >= 30:
        level = "high"
    elif score >= 10:
        level = "medium"
    else:
        level = "low"

    return RiskAssessment(level=level, reasons=tuple(reasons), score=min(score, 100))


def decide_action(mode: "ReplyMode", assessment: RiskAssessment) -> ActionDecision:
    """根据回复模式和风险评估决定操作"""
    if assessment.level == "high":
        return ActionDecision(
            action="block",
            reason=f"高风险内容，禁止自动发送: {'; '.join(assessment.reasons[:2])}",
        )

    if mode == "suggest":
        return ActionDecision(action="confirm", reason="建议模式，需要人工确认")

    if mode == "auto":
        if assessment.level == "low":
            return ActionDecision(action="auto_send", reason="自动模式，低风险，自动发送")
        return ActionDecision(action="confirm", reason=f"自动模式，{assessment.level}风险，需确认")

    # hybrid 模式（默认）
    if assessment.level == "low":
        return ActionDecision(action="auto_send", reason="混合模式，低风险，自动发送")
    elif assessment.level == "medium":
        return ActionDecision(action="confirm", reason="混合模式，中风险，需要确认")
    else:
        return ActionDecision(action="block", reason="混合模式，高风险，禁止发送")
