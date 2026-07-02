import pytest

from support_agent_lab.agent.orchestrator import SupportAgentOrchestrator
from support_agent_lab.data.fixtures import DemoStore
from support_agent_lab.llm.gateway import create_default_llm_gateway
from support_agent_lab.memory.event_store import SQLiteEventStore
from support_agent_lab.memory.store import ConversationMemory, KnowledgeIndex
from support_agent_lab.monitoring.monitor import OnlineMonitorAgent
from support_agent_lab.tools.business_tools import create_registry
from support_agent_lab.tools.registry import ToolBroker


@pytest.mark.asyncio
async def test_orchestrator_writes_append_only_events(tmp_path):
    store = DemoStore.seeded()
    knowledge = KnowledgeIndex()
    event_store = SQLiteEventStore(tmp_path / "events.db")
    tools = ToolBroker(
        registry=create_registry(store, knowledge),
        idempotency_store=store.idempotency,
    )
    orchestrator = SupportAgentOrchestrator(
        tenant_id="demo_tenant",
        memory=ConversationMemory(),
        knowledge=knowledge,
        tools=tools,
        llm=create_default_llm_gateway(),
        event_store=event_store,
        monitor=OnlineMonitorAgent(),
    )

    response = await orchestrator.handle_message(
        conversation_id="conv_events",
        user_id="user_demo",
        text="\u6211\u8ba2\u5355 A1001 \u7684\u8033\u673a\u574f\u4e86\uff0c\u80fd\u9000\u5417\uff1f",
    )

    events = event_store.list_events(conversation_id="conv_events")
    event_types = [event.event_type for event in events]
    assert event_types == [
        "message.user",
        "message.assistant",
        "agent.run.completed",
        "monitor.reviewed",
    ]
    run_event = [event for event in events if event.event_type == "agent.run.completed"][0]
    assert run_event.payload["id"] == response.trace.id
    assert run_event.payload["tool_results"]
    assert run_event.payload["llm_calls"]

