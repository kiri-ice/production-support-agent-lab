from __future__ import annotations

from support_agent_lab.models import AgentPlan, IntentResult, IntentType, RouteTarget, ToolRequest


RETURN_QUERY = "\u9000\u6362\u8d27\u653f\u7b56 \u8d28\u91cf\u95ee\u9898 30 \u5929"
SHIPPING_QUERY = "\u7269\u6d41\u653f\u7b56 \u5ef6\u8fdf \u67e5\u8be2"
BILLING_QUERY = "\u53d1\u7968 \u8d26\u5355 \u7a0e\u53f7 \u62ac\u5934"
TECH_QUERY_SUFFIX = "\u6545\u969c \u6392\u67e5"
COMPLAINT_QUERY = "\u5ba2\u670d \u6295\u8bc9 \u5347\u7ea7 \u4eba\u5de5"
SECURITY_QUERY = "\u8d26\u53f7\u5b89\u5168 \u9690\u79c1 \u4eba\u5de5\u5347\u7ea7"


class DomainAgent:
    target: RouteTarget = RouteTarget.general_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        raise NotImplementedError


class OrderAgent(DomainAgent):
    target = RouteTarget.order_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        requests = [ToolRequest(name="crm.get_customer", arguments={"user_id": user_id}, reason="Identify customer")]
        order_id = intent.entities.get("order_id") or intent.entities.get("last_order_id")
        if order_id:
            requests.append(ToolRequest(name="order.get", arguments={"order_id": order_id}, reason="Fetch referenced order"))
            if intent.primary == IntentType.refund_or_return:
                requests.append(
                    ToolRequest(
                        name="ticket.create",
                        arguments={
                            "customer_id": "SELF",
                            "title": f"After-sales review for order {order_id}",
                            "description": user_text,
                            "priority": "normal",
                            "tags": ["return_or_refund", "quality_issue"],
                        },
                        reason="Create after-sales ticket instead of directly refunding money",
                    )
                )
        else:
            requests.append(
                ToolRequest(
                    name="order.search",
                    arguments={"customer_id": "SELF"},
                    reason="Find candidate orders when user omitted order id",
                )
            )
        query = RETURN_QUERY if intent.primary == IntentType.refund_or_return else SHIPPING_QUERY
        return AgentPlan(
            target_agent=self.target,
            tool_requests=requests,
            retrieval_query=query,
            response_goal="Resolve order, return, refund, or shipping question with source-backed policy.",
        )


class BillingAgent(DomainAgent):
    target = RouteTarget.billing_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        order_id = intent.entities.get("order_id") or intent.entities.get("last_order_id")
        requests = [ToolRequest(name="crm.get_customer", arguments={"user_id": user_id}, reason="Identify customer")]
        if order_id:
            requests.append(ToolRequest(name="order.get", arguments={"order_id": order_id}, reason="Fetch billing order"))
        return AgentPlan(
            target_agent=self.target,
            tool_requests=requests,
            retrieval_query=BILLING_QUERY,
            response_goal="Answer invoice or billing question and create a ticket if data must be changed.",
        )


class TechAgent(DomainAgent):
    target = RouteTarget.tech_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        return AgentPlan(
            target_agent=self.target,
            tool_requests=[ToolRequest(name="crm.get_customer", arguments={"user_id": user_id}, reason="Identify customer")],
            retrieval_query=f"{user_text} {TECH_QUERY_SUFFIX}",
            response_goal="Give safe troubleshooting steps and connect to after-sales flow when needed.",
        )


class RetentionAgent(DomainAgent):
    target = RouteTarget.retention_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        return AgentPlan(
            target_agent=self.target,
            tool_requests=[
                ToolRequest(name="crm.get_customer", arguments={"user_id": user_id}, reason="Identify customer"),
                ToolRequest(
                    name="ticket.create",
                    arguments={
                        "customer_id": "SELF",
                        "title": "Customer complaint requires review",
                        "description": user_text,
                        "priority": "high",
                        "tags": ["complaint", "handoff"],
                    },
                    reason="Create human follow-up ticket for complaint",
                ),
            ],
            retrieval_query=COMPLAINT_QUERY,
            handoff_reason="Complaint or angry sentiment needs human follow-up.",
            response_goal="Acknowledge frustration, avoid arguing, and hand off with context.",
        )


class SafetyAgent(DomainAgent):
    target = RouteTarget.safety_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        return AgentPlan(
            target_agent=self.target,
            tool_requests=[
                ToolRequest(
                    name="ticket.create",
                    arguments={
                        "customer_id": "SELF",
                        "title": "Security or policy-sensitive conversation",
                        "description": user_text,
                        "priority": "urgent",
                        "tags": ["security", "policy_review"],
                    },
                    reason="Create a security review ticket",
                )
            ],
            retrieval_query=SECURITY_QUERY,
            handoff_reason="Security, privacy, or prompt-injection risk.",
            response_goal="Limit disclosure and route to a verified human process.",
        )


class GeneralAgent(DomainAgent):
    target = RouteTarget.general_agent

    def plan(self, intent: IntentResult, user_text: str, user_id: str) -> AgentPlan:
        return AgentPlan(
            target_agent=self.target,
            tool_requests=[ToolRequest(name="crm.get_customer", arguments={"user_id": user_id}, reason="Identify customer")],
            retrieval_query=user_text,
            response_goal="Answer with knowledge-base grounding or ask a concise clarifying question.",
        )


AGENTS: dict[RouteTarget, DomainAgent] = {
    RouteTarget.order_agent: OrderAgent(),
    RouteTarget.billing_agent: BillingAgent(),
    RouteTarget.tech_agent: TechAgent(),
    RouteTarget.retention_agent: RetentionAgent(),
    RouteTarget.safety_agent: SafetyAgent(),
    RouteTarget.general_agent: GeneralAgent(),
}

