from __future__ import annotations

from support_agent_lab.models import AgentResponse, MonitorEvent, RiskLevel, ToolStatus


class OnlineMonitorAgent:
    def __init__(self) -> None:
        self.events: list[MonitorEvent] = []

    def review(self, response: AgentResponse) -> MonitorEvent:
        trace = response.trace
        assert trace.intent is not None
        policy_failures = [finding for finding in trace.policy_findings if finding.should_block or finding.should_escalate]
        tool_failures = [tool for tool in trace.tool_results if tool.status == ToolStatus.failed]
        has_citations = bool(response.citations)
        needs_review = bool(policy_failures or tool_failures or response.handoff_required)
        risk = RiskLevel.low
        if any(finding.risk_level in {RiskLevel.high, RiskLevel.critical} for finding in trace.policy_findings):
            risk = RiskLevel.high
        elif needs_review:
            risk = RiskLevel.medium
        event = MonitorEvent(
            conversation_id=trace.conversation_id,
            run_id=trace.id,
            agent_version=trace.agent_version,
            user_intent=trace.intent.primary,
            risk_level=risk,
            grounded=has_citations or trace.intent.primary.value in {"complaint", "account_security"},
            policy_compliant=not policy_failures,
            pii_leak=False,
            needs_human_review=needs_review,
            failure_types=[*(finding.code for finding in policy_failures), *(tool.error_code or "TOOL_FAILED" for tool in tool_failures)],
            summary=self._summarize(response),
        )
        self.events.append(event)
        return event

    def _summarize(self, response: AgentResponse) -> str:
        intent = response.trace.intent.primary.value if response.trace.intent else "unknown"
        tools = ", ".join(tool.name for tool in response.trace.tool_results) or "no tools"
        return f"intent={intent}; tools={tools}; handoff={response.handoff_required}"

