from __future__ import annotations

from support_agent_lab.models import IntentResult, IntentType, RiskLevel, RouteDecision, RouteTarget
from support_agent_lab.agent.policy import PolicyEngine


class AgentRouter:
    def __init__(self, policy: PolicyEngine) -> None:
        self.policy = policy

    def route(self, intent: IntentResult, policy_risk: RiskLevel = RiskLevel.low) -> RouteDecision:
        if policy_risk in {RiskLevel.high, RiskLevel.critical}:
            return RouteDecision(
                target=RouteTarget.safety_agent,
                reason="High policy risk; route to safety/handoff path.",
                allowed_tools=["crm.get_customer", "ticket.create", "kb.search"],
                needs_human=True,
            )
        if intent.sentiment == "angry" or intent.primary == IntentType.complaint:
            return RouteDecision(
                target=RouteTarget.retention_agent,
                reason="Complaint or angry sentiment needs retention/human-aware handling.",
                allowed_tools=self.policy.allowed_tools_for(intent.primary),
                needs_human=True,
            )
        mapping = {
            IntentType.refund_or_return: RouteTarget.order_agent,
            IntentType.order_status: RouteTarget.order_agent,
            IntentType.billing: RouteTarget.billing_agent,
            IntentType.technical_issue: RouteTarget.tech_agent,
            IntentType.account_security: RouteTarget.safety_agent,
            IntentType.general_question: RouteTarget.general_agent,
            IntentType.unknown: RouteTarget.general_agent,
        }
        target = mapping.get(intent.primary, RouteTarget.general_agent)
        return RouteDecision(
            target=target,
            reason=f"Intent {intent.primary.value} mapped to {target.value}.",
            allowed_tools=self.policy.allowed_tools_for(intent.primary),
            needs_human=target == RouteTarget.safety_agent,
        )

