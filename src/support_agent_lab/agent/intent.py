from __future__ import annotations

import re

from support_agent_lab.models import IntentResult, IntentType


class IntentDetector:
    def detect(self, text: str, known_facts: dict | None = None) -> IntentResult:
        normalized = text.lower()
        known_facts = known_facts or {}
        entities = dict(known_facts)
        order_match = re.search(r"\b[A-Z]\d{4,}\b", text.upper())
        if order_match:
            entities["order_id"] = order_match.group(0)

        candidates: list[tuple[IntentType, float, str]] = []
        if self._has(normalized, ["退款", "退货", "换货", "坏了", "质量问题", "return", "refund"]):
            candidates.append((IntentType.refund_or_return, 0.88, "refund/return keywords"))
        if self._has(normalized, ["物流", "快递", "到哪", "发货", "shipment", "shipping"]):
            candidates.append((IntentType.order_status, 0.84, "shipping/order keywords"))
        if self._has(normalized, ["发票", "账单", "扣款", "付款", "invoice", "billing"]):
            candidates.append((IntentType.billing, 0.84, "billing keywords"))
        if self._has(normalized, ["故障", "不能用", "无声", "蓝牙", "报错", "bug", "broken"]):
            candidates.append((IntentType.technical_issue, 0.80, "technical support keywords"))
        if self._has(normalized, ["投诉", "生气", "客服", "差评", "complaint", "angry"]):
            candidates.append((IntentType.complaint, 0.86, "complaint/escalation keywords"))
        if self._has(normalized, ["被盗", "异常登录", "密码", "账号", "security", "stolen"]):
            candidates.append((IntentType.account_security, 0.90, "security keywords"))

        if not candidates:
            return IntentResult(
                primary=IntentType.general_question,
                confidence=0.62,
                entities=entities,
                rationale="No strong domain keyword; route to general agent with retrieval.",
            )

        candidates.sort(key=lambda item: item[1], reverse=True)
        primary, confidence, rationale = candidates[0]
        missing_slots: list[str] = []
        if primary in {IntentType.refund_or_return, IntentType.order_status, IntentType.billing}:
            if "order_id" not in entities and "last_order_id" not in entities:
                missing_slots.append("order_id")

        sentiment = "angry" if self._has(normalized, ["投诉", "生气", "差评", "angry"]) else "calm"
        urgency = "urgent" if self._has(normalized, ["马上", "立即", "现在", "urgent"]) else "normal"
        return IntentResult(
            primary=primary,
            secondary=[intent for intent, _, _ in candidates[1:]],
            confidence=confidence,
            entities=entities,
            missing_slots=missing_slots,
            sentiment=sentiment,
            urgency=urgency,
            rationale=rationale,
        )

    def _has(self, text: str, words: list[str]) -> bool:
        return any(word in text for word in words)

