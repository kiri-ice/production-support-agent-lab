from __future__ import annotations

import re

from support_agent_lab.models import IntentType, PolicyFinding, RiskLevel


class PolicyEngine:
    PII_RE = re.compile(r"(\b1[3-9]\d{9}\b)|([\w.+-]+@[\w.-]+\.[a-zA-Z]{2,})")
    PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")
    EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[a-zA-Z]{2,}")

    def check_input(self, text: str) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []
        lowered = text.lower()
        if self.PII_RE.search(text):
            findings.append(
                PolicyFinding(
                    code="PII_IN_INPUT",
                    risk_level=RiskLevel.medium,
                    message="User input contains possible PII; store redacted copy in production.",
                )
            )
        injection_markers = [
            "ignore previous",
            "\u5ffd\u7565\u4e4b\u524d",  # ignore previous
            "\u6cc4\u9732",  # leak
            "\u7cfb\u7edf\u63d0\u793a",  # system prompt
        ]
        if any(marker in lowered for marker in injection_markers):
            findings.append(
                PolicyFinding(
                    code="PROMPT_INJECTION_ATTEMPT",
                    risk_level=RiskLevel.high,
                    message="Prompt injection pattern detected.",
                    should_escalate=True,
                )
            )
        return findings

    def redact_pii(self, text: str) -> str:
        redacted = self.PHONE_RE.sub("[REDACTED_PHONE]", text)
        return self.EMAIL_RE.sub("[REDACTED_EMAIL]", redacted)

    def allowed_tools_for(self, intent: IntentType) -> list[str]:
        base = ["crm.get_customer", "kb.search", "ticket.create"]
        if intent in {IntentType.refund_or_return, IntentType.order_status, IntentType.billing}:
            return base + ["order.search", "order.get", "shipping.track"]
        if intent == IntentType.technical_issue:
            return base + ["order.search", "order.get"]
        if intent == IntentType.account_security:
            return ["crm.get_customer", "ticket.create", "kb.search"]
        return base

    def check_output(self, text: str, high_risk: bool = False) -> list[PolicyFinding]:
        findings: list[PolicyFinding] = []
        forbidden_promises = [
            "\u65e0\u6761\u4ef6\u9000\u6b3e",  # unconditional refund
            "\u4e00\u5b9a\u8d54\u4ed8",  # guaranteed compensation
        ]
        if any(promise in text for promise in forbidden_promises):
            findings.append(
                PolicyFinding(
                    code="UNSUPPORTED_COMPENSATION_PROMISE",
                    risk_level=RiskLevel.high,
                    message="Response makes a compensation promise not grounded in policy.",
                    should_escalate=True,
                )
            )
        if self.PII_RE.search(text):
            findings.append(
                PolicyFinding(
                    code="PII_IN_OUTPUT",
                    risk_level=RiskLevel.critical,
                    message="Assistant output contains possible PII.",
                    should_escalate=True,
                )
            )
        if high_risk and "\u4eba\u5de5" not in text:
            findings.append(
                PolicyFinding(
                    code="HIGH_RISK_WITHOUT_HANDOFF",
                    risk_level=RiskLevel.medium,
                    message="High-risk response should mention human review or handoff.",
                )
            )
        return findings
