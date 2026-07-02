from __future__ import annotations

from dataclasses import dataclass

from support_agent_lab.agent.orchestrator import SupportAgentOrchestrator
from support_agent_lab.config import get_settings
from support_agent_lab.data.fixtures import DemoStore
from support_agent_lab.memory.store import ConversationMemory, KnowledgeIndex
from support_agent_lab.monitoring.monitor import OnlineMonitorAgent
from support_agent_lab.tools.business_tools import create_registry
from support_agent_lab.tools.registry import ToolBroker


@dataclass
class AppContainer:
    store: DemoStore
    memory: ConversationMemory
    knowledge: KnowledgeIndex
    monitor: OnlineMonitorAgent
    tools: ToolBroker
    orchestrator: SupportAgentOrchestrator


def create_container() -> AppContainer:
    settings = get_settings()
    store = DemoStore.seeded()
    memory = ConversationMemory()
    knowledge = KnowledgeIndex()
    monitor = OnlineMonitorAgent()
    registry = create_registry(store, knowledge)
    tools = ToolBroker(registry=registry, idempotency_store=store.idempotency)
    orchestrator = SupportAgentOrchestrator(
        tenant_id=settings.app_tenant_id,
        memory=memory,
        knowledge=knowledge,
        tools=tools,
        monitor=monitor,
    )
    return AppContainer(
        store=store,
        memory=memory,
        knowledge=knowledge,
        monitor=monitor,
        tools=tools,
        orchestrator=orchestrator,
    )

